"""Testes da leitura determinística de CSVs."""

from io import BytesIO

import pandas as pd
import pytest

from iica_csv.processing.csv_reader import CSVFormatError, read_csv
from iica_csv.processing.data_manager import DataManager, DatasetNotFoundError


def test_reads_utf8_comma_and_dot_decimal_preserving_identifier() -> None:
    content = (
        "CHAVE DE ACESSO,DATA EMISSÃO,DESCRIÇÃO DO PRODUTO/SERVIÇO,VALOR TOTAL\r\n"
        '001234,2024-01-18 07:10:39,"Peça, grande",10.50\r\n'
        "009999,2024-01-19 08:00:00,Serviço,2.00\r\n"
    ).encode("utf-8")

    result = read_csv(content, filename="itens.csv")

    assert result.encoding == "utf-8"
    assert result.separator == ","
    assert result.decimal == "."
    assert result.dataframe.loc[0, "CHAVE DE ACESSO"] == "001234"
    assert result.dataframe.loc[0, "DESCRIÇÃO DO PRODUTO/SERVIÇO"] == "Peça, grande"
    assert result.dataframe.loc[0, "VALOR TOTAL"] == pytest.approx(10.5)
    assert pd.api.types.is_datetime64_any_dtype(result.dataframe["DATA EMISSÃO"])


def test_reads_cp1252_semicolon_and_comma_decimal() -> None:
    content = (
        "CHAVE DE ACESSO;RAZÃO SOCIAL EMITENTE;DATA EMISSÃO;VALOR NOTA FISCAL;QUANTIDADE\r\n"
        "000123;Ação Comércio;01/05/2025 00:00:00;1.234,56;2,00\r\n"
        "000124;Órbita Ltda;02/05/2025 10:30:00;10,00;3,50\r\n"
    ).encode("cp1252")

    result = read_csv(BytesIO(content), filename="notas.csv")

    assert result.encoding == "cp1252"
    assert result.separator == ";"
    assert result.decimal == ","
    assert result.dataframe.loc[0, "CHAVE DE ACESSO"] == "000123"
    assert result.dataframe.loc[0, "VALOR NOTA FISCAL"] == pytest.approx(1234.56)
    assert result.dataframe.loc[1, "QUANTIDADE"] == pytest.approx(3.5)
    assert pd.api.types.is_datetime64_any_dtype(result.dataframe["DATA EMISSÃO"])


def test_reads_utf8_with_bom() -> None:
    result = read_csv("NOME,VALOR TOTAL\nA,1.5\n".encode("utf-8-sig"))

    assert result.encoding == "utf-8-sig"
    assert result.dataframe.loc[0, "VALOR TOTAL"] == pytest.approx(1.5)


def test_falls_back_to_latin1_when_cp1252_cannot_decode() -> None:
    result = read_csv(b"NOME,DESCRICAO\nA,\x81\n")

    assert result.encoding == "latin-1"
    assert result.dataframe.loc[0, "DESCRICAO"] == "\x81"


def test_file_like_position_is_restored() -> None:
    stream = BytesIO(b"CODIGO,VALOR\n001,1.5\n")
    stream.seek(4)

    result = read_csv(stream)

    assert result.dataframe.loc[0, "CODIGO"] == "001"
    assert stream.tell() == 4


def test_rejects_csv_interpreted_as_one_column() -> None:
    with pytest.raises(CSVFormatError, match="estrutura válida|única coluna"):
        read_csv(b"nome\nAna\nBruno\n")


def test_rejects_empty_and_binary_files() -> None:
    with pytest.raises(CSVFormatError, match="vazio"):
        read_csv(b"")
    with pytest.raises(CSVFormatError, match="texto"):
        read_csv(b"A,B\x00\x01\n1,2")


def test_unsafe_conversion_keeps_original_column() -> None:
    content = (
        "ITEM,DATA EMISSÃO,VALOR TOTAL\n"
        "A,2024-01-01 00:00:00,10.0\n"
        "B,data desconhecida,não informado\n"
    ).encode("utf-8")

    dataframe = read_csv(content).dataframe

    assert dataframe["VALOR TOTAL"].tolist() == ["10.0", "não informado"]
    assert dataframe["DATA EMISSÃO"].tolist() == [
        "2024-01-01 00:00:00",
        "data desconhecida",
    ]


def test_data_manager_exposes_rich_metadata_and_friendly_lookup() -> None:
    result = read_csv(b"ID,VALOR TOTAL\n001,2.5\n002,\n")
    manager = DataManager()
    manager.add_dataset(
        "vendas",
        result,
        source_name="pasta/vendas.csv",
        data_dictionary={
            "descricao": "Vendas da demonstração",
            "colunas": {"VALOR TOTAL": {"descricao": "Valor monetário"}},
        },
    )

    metadata = manager.get_metadata("vendas.csv")
    assert manager.has_data
    assert len(manager) == 1
    assert manager.dataset_names == ["vendas"]
    assert metadata["rows"] == 2
    assert metadata["columns_count"] == 2
    assert metadata["null_counts"]["VALOR TOTAL"] == 1
    assert metadata["encoding"] == "utf-8"
    assert metadata["column_descriptions"]["VALOR TOTAL"] == "Valor monetário"
    with pytest.raises(DatasetNotFoundError, match="Disponíveis"):
        manager.get_dataframe("inexistente")
