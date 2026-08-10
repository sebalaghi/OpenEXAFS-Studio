from openexafs_studio.core import PathRecord, safe_filename, structure_format_from_path


def test_path_kind():
    ss = PathRecord(1, "feff0001.dat", 2, 4.0, 2.0, "Pt - O")
    ms = PathRecord(2, "feff0002.dat", 3, 2.0, 3.0, "Pt - O - Pt")
    assert ss.kind == "SS"
    assert ms.kind == "MS"


def test_safe_filename():
    assert safe_filename("Pt path #1 / O") == "Pt_path_1_O"


def test_structure_format():
    assert structure_format_from_path("sample.cif") == "cif"
    assert structure_format_from_path("POSCAR") == "poscar"
