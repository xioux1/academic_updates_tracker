from normalization import (
    normalize_date,
    normalize_department_name,
    normalize_language,
    normalize_program_name,
    normalize_program_payload,
    normalize_tuition,
)


def test_normalize_language_to_closed_taxonomy():
    assert normalize_language("English")["normalized"] == "en"
    assert normalize_language("英语")["normalized"] == "en"
    assert normalize_language("中文")["normalized"] == "zh"
    assert normalize_language("English / Chinese")["normalized"] == "bilingual"
    assert normalize_language("Klingon")["normalized"] == "unknown"
    assert normalize_language("Klingon")["ambiguous"] is True


def test_normalize_date_to_iso():
    assert normalize_date("15 Jan 2027")["normalized"] == "2027-01-15"
    assert normalize_date("January 5, 2027")["normalized"] == "2027-01-05"
    assert normalize_date("2027年3月1日")["normalized"] == "2027-03-01"
    assert normalize_date("2027/3/1")["normalized"] == "2027-03-01"
    assert normalize_date("rolling basis")["normalized"] is None
    assert normalize_date("2027-03-01 to 2027-03-10")["ambiguous"] is True


def test_normalize_tuition_to_amount_plus_currency():
    normalized = normalize_tuition("USD 12,500 /year")
    assert normalized["normalized"] == {
        "amount": 12500.0,
        "currency": "USD",
        "periodicity": "annual",
    }
    assert normalized["ambiguous"] is False
    zh_tuition = normalize_tuition("学费：¥45,000 每年")
    assert zh_tuition["normalized"] == {
        "amount": 45000.0,
        "currency": "CNY",
        "periodicity": "annual",
    }
    assert zh_tuition["ambiguous"] is False
    per_semester = normalize_tuition("USD 8,500 per semester")
    assert per_semester["normalized"] == {
        "amount": 8500.0,
        "currency": "USD",
        "periodicity": "semester",
    }
    total_tuition = normalize_tuition("RMB 120,000 total")
    assert total_tuition["normalized"] == {
        "amount": 120000.0,
        "currency": "CNY",
        "periodicity": "total",
    }
    ambiguous_range = normalize_tuition("USD 12,000-18,000 /year")
    assert ambiguous_range["normalized"] is None
    assert ambiguous_range["ambiguous"] is True


def test_variant_mapping_for_program_and_department_names():
    assert normalize_program_name("M.Sc. in Data Science")["normalized"] == "MSc Data Science"
    assert normalize_department_name("Dept. of Computer Science")["normalized"] == "Department of Computer Science"
    assert normalize_program_name("人工智能硕士")["normalized"] == "MSc Artificial Intelligence"
    assert normalize_program_name("Master of Science in Artificial Intelligence")["normalized"] == "MSc Artificial Intelligence"
    assert normalize_program_name("M.Eng. in Electronic Information")["normalized"] == "MEng Electronic Information"
    assert (
        normalize_department_name("School of Computer Science & Engineering")["normalized"]
        == "School of Computer Science"
    )
    assert (
        normalize_department_name("Computer Science and Engineering Department")["normalized"]
        == "Department of Computer Science"
    )
    assert (
        normalize_department_name("电子信息与电气工程学院")["normalized"]
        == "School of Electronic and Information Engineering"
    )


def test_program_payload_includes_official_vs_derived_and_ambiguity_flags():
    payload = normalize_program_payload(
        {
            "name": "M.Sc. in Data Science",
            "department_name": "Dept. of Computer Science",
            "critical_fields": {
                "language": "English",
                "deadlines": "15 Jan 2027",
                "tuition": "USD 12,500 /year",
            },
        }
    )

    assert payload["canonical_name"] == "MSc Data Science"
    assert payload["official_data"]["critical_fields"]["language"]["raw"] == "English"
    assert payload["derived_data"]["critical_fields"]["language"]["normalized"] == "en"
    assert payload["derived_data"]["critical_fields"]["deadlines"]["normalized"] == "2027-01-15"
    assert payload["derived_data"]["ambiguity_flags"]["language"] is False
