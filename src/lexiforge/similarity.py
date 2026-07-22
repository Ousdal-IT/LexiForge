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


def longest_common_substring_length(left: str, right: str) -> int:
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, 1):
            value = previous[index - 1] + 1 if left_char == right_char else 0
            current.append(value)
            longest = max(longest, value)
        previous = current
    return longest


def find_similar_words(
    records: list[CandidateRecord], profile: LanguageProfile
) -> list[SimilarityFinding]:
    words = sorted({normalize_word(record.candidate.word, profile) for record in records})
    findings = []
    for index, left in enumerate(words):
        for right in words[index + 1 :]:
            distance = damerau_levenshtein(left, right)
            common_prefix = 0
            for a, b in zip(left, right, strict=False):
                if a != b:
                    break
                common_prefix += 1
            common_suffix = 0
            for a, b in zip(reversed(left), reversed(right), strict=False):
                if a != b:
                    break
                common_suffix += 1
            vowel_set = set(profile.vowels)
            left_skeleton = "".join(char for char in left if char not in vowel_set)
            right_skeleton = "".join(char for char in right if char not in vowel_set)
            visual_translation = str.maketrans({"i": "l", "m": "n"})
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
            elif distance == 1:
                rule = "similarity.edit_distance_1"
            elif common_prefix >= 3:
                rule = "similarity.repeated_prefix"
            elif common_suffix >= 3:
                rule = "similarity.repeated_suffix"
            elif longest_common_substring_length(left, right) >= 3:
                rule = "similarity.repeated_stem"
            elif left_skeleton == right_skeleton and left_skeleton:
                rule = "similarity.phonetic_skeleton"
            elif left.translate(visual_translation) == right.translate(visual_translation):
                rule = "similarity.visual_shape"
            else:
                continue
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
