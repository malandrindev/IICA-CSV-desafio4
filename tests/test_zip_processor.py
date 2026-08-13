"""Testes do processamento seguro de pacotes ZIP."""

from io import BytesIO
import json
import stat
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from iica_csv.processing.zip_processor import (
    CSVNotFoundError,
    InvalidZipError,
    MISSING_DICTIONARY_WARNING,
    ZipLimitError,
    ZipProcessor,
    ZipSecurityError,
)


def make_zip(files: dict[str, bytes | str]) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return target.getvalue()


def test_processes_nested_multiple_csvs_and_json_dictionary() -> None:
    dictionary = {
        "versao": 1,
        "datasets": {
            "cabecalho.csv": {
                "descricao": "Notas fiscais",
                "colunas": {
                    "VALOR NOTA FISCAL": {
                        "descricao": "Valor total da nota",
                        "tipo_semantico": "monetario",
                    }
                },
            },
            "itens.csv": {
                "descricao": "Itens das notas",
                "colunas": {"QUANTIDADE": {"descricao": "Volume comprado"}},
            },
        },
    }
    package_bytes = make_zip(
        {
            "dados/cabecalho.csv": "CHAVE DE ACESSO,VALOR NOTA FISCAL\n001,10.5\n",
            "dados/itens.csv": "CHAVE DE ACESSO,QUANTIDADE\n001,2.0\n",
            "documentacao/dicionario_dados.json": json.dumps(
                dictionary, ensure_ascii=False
            ).encode("utf-8"),
        }
    )

    package = ZipProcessor().process(package_bytes, filename="pacote.ZIP")

    assert package.dictionary_found is True
    assert package.csv_files == ["dados/cabecalho.csv", "dados/itens.csv"]
    assert package.dictionary_files == ["documentacao/dicionario_dados.json"]
    assert package.data_manager.dataset_names == ["cabecalho", "itens"]
    assert package.data_manager.get_metadata("cabecalho")["description"] == "Notas fiscais"
    assert (
        package.data_manager.get_metadata("cabecalho")["column_descriptions"]
        ["VALOR NOTA FISCAL"]
        == "Valor total da nota"
    )


def test_dictionary_csv_is_loaded_and_related() -> None:
    package_bytes = make_zip(
        {
            "dados.csv": "ID,VALOR TOTAL\n001,5.0\n",
            "dicionario_dados.csv": (
                "arquivo,coluna,descricao,tipo_semantico\n"
                "dados.csv,VALOR TOTAL,Valor monetário,monetario\n"
            ),
        }
    )

    package = ZipProcessor().process(package_bytes, filename="pacote.zip")

    metadata = package.data_manager.get_metadata("dados")
    assert package.dictionary_found
    assert metadata["column_descriptions"]["VALOR TOTAL"] == "Valor monetário"


def test_missing_dictionary_is_a_warning_not_an_error() -> None:
    package = ZipProcessor().process(
        make_zip({"dados.csv": "ID,VALOR\n001,1.0\n"}),
        filename="dados.zip",
    )

    assert not package.dictionary_found
    assert package.dictionary_files == []
    assert package.warnings == [MISSING_DICTIONARY_WARNING]
    assert package.data_manager.has_data


def test_rejects_package_without_analytical_csv() -> None:
    with pytest.raises(CSVNotFoundError, match="Nenhum arquivo CSV"):
        ZipProcessor().process(
            make_zip({"README.txt": "sem dados"}), filename="vazio.zip"
        )


def test_rejects_non_zip_content_and_wrong_extension() -> None:
    processor = ZipProcessor()
    with pytest.raises(InvalidZipError, match="assinatura ZIP"):
        processor.process("isto não é zip".encode("utf-8"), filename="dados.zip")
    with pytest.raises(InvalidZipError, match="extensão .zip"):
        processor.process(make_zip({"dados.csv": "A,B\n1,2\n"}), filename="dados.csv")


@pytest.mark.parametrize("unsafe_name", ["../evil.csv", "pasta/../../evil.csv", "..\\evil.csv"])
def test_rejects_zip_slip(unsafe_name: str) -> None:
    with pytest.raises(ZipSecurityError, match="Caminho inseguro"):
        ZipProcessor().process(
            make_zip({unsafe_name: "A,B\n1,2\n"}), filename="dados.zip"
        )


def test_rejects_symbolic_link() -> None:
    target = BytesIO()
    link = ZipInfo("dados.csv")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(target, "w") as archive:
        archive.writestr(link, "destino.csv")

    with pytest.raises(ZipSecurityError, match="Links simbólicos"):
        ZipProcessor().process(target.getvalue(), filename="dados.zip")


def test_rejects_case_insensitive_duplicate_entries() -> None:
    target = BytesIO()
    with ZipFile(target, "w") as archive:
        archive.writestr("dados.csv", "A,B\n1,2\n")
        archive.writestr("DADOS.CSV", "A,B\n3,4\n")

    with pytest.raises(ZipSecurityError, match="duplicada"):
        ZipProcessor().process(target.getvalue(), filename="dados.zip")


def test_rejects_suspicious_compression_ratio() -> None:
    compressed = make_zip({"dados.csv": "A,B\n" + ("1,1\n" * 10_000)})

    with pytest.raises(ZipLimitError, match="compressão suspeita"):
        ZipProcessor(max_compression_ratio=2).process(
            compressed, filename="dados.zip"
        )


def test_rejects_dictionary_above_its_specific_limit() -> None:
    package = make_zip(
        {
            "dados.csv": "A,B\n1,2\n",
            "dicionario.json": '{"descricao":"' + ("x" * 2_000) + '"}',
        }
    )

    with pytest.raises(ZipLimitError, match="dicionário"):
        ZipProcessor(max_dictionary_mb=0.001).process(
            package, filename="dados.zip"
        )
