from .models import CandidateRecord, LanguageProfile, SimilarityFinding
from .normalize import normalize_word


def damerau_levenshtein(left: str, right: str) -> int:
    matrix = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for index in range(len(left) + 1):
        matrix[index][0] = index
    for index in range(len(right) + 1):
        matrix[0][index] = index
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            cost = int(left[i - 1] != right[j - 1])
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )
            if i > 1 and j > 1 and left[i - 1] == right[j - 2] and left[i - 2] == right[j - 1]:
                matrix[i][j] = min(matrix[i][j], matrix[i - 2][j - 2] + 1)
    return matrix[-1][-1]


def find_similar_words(
    records: list[CandidateRecord], profile: LanguageProfile
) -> list[SimilarityFinding]:
    words = sorted({normalize_word(record.candidate.word, profile) for record in records})
    findings = []
    for index, left in enumerate(words):
        for right in words[index + 1 :]:
            distance = damerau_levenshtein(left, right)
            if distance > 1:
                continue
            if distance == 0:
                rule = "similarity.exact"
            elif len(left) == len(right) and any(
                left[i : i + 2] == right[i : i + 2][::-1] for i in range(len(left) - 1)
            ):
                rule = "similarity.transposition"
            elif (
                left.startswith(right)
                or right.startswith(left)
                or left.endswith(right)
                or right.endswith(left)
            ):
                rule = "similarity.affix"
            else:
                rule = "similarity.edit_distance_1"
            findings.append(
                SimilarityFinding(
                    language=profile.code,
                    word_a=left,
                    word_b=right,
                    rule_id=rule,
                    distance=distance,
                    explanation=(
                        "Potentially confusing normalized spellings; human review required."
                    ),
                )
            )
    return findings
