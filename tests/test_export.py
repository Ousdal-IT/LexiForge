from lexiforge.export import approved_words, export_bytes


def test_txt_exact_bytes(nb_records, nb_profile) -> None:
    words = approved_words(nb_records, nb_profile)
    assert export_bytes(words, nb_profile, "txt") == (
        "bjørn\nbåten\neple\nskog\nstol\n væske\n".replace(" ", "").encode()
    )


def test_json_and_csv_are_stable(nb_records, nb_profile) -> None:
    words = approved_words(nb_records, nb_profile)
    json_data = export_bytes(words, nb_profile, "json")
    csv_data = export_bytes(words, nb_profile, "csv")
    assert json_data.endswith(b"\n") and b'"language": "nb"' in json_data
    assert csv_data.startswith(b"language,word\n") and csv_data.endswith(b"\n")
    assert export_bytes(words, nb_profile, "json") == json_data


def test_approved_only(nb_records, nb_profile) -> None:
    assert "hoppe" not in approved_words(nb_records, nb_profile)
