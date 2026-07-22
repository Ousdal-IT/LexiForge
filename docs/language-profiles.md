# Language profiles

Every `data/languages/<code>/language.yaml` strictly declares its code, display name, locale, Unicode normalization, length range, anchored allowed-character regex, punctuation/digit/whitespace permissions, output case, and target sizes. Unknown keys, malformed codes, invalid regexes, and unsupported values fail configuration loading.

M0 profiles are `nb`, `nn`, and `en`. Norwegian permits lowercase `a-z`, `æ`, `ø`, and `å`; English permits lowercase ASCII `a-z`. Profiles can later represent `da`, `sv`, `is`, `de`, `fr`, `en-GB`, or `en-US` without core rule branches.

