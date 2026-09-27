"""Credential removal for export copies only; raw matching values never logged."""
import re

RULES = [
    ('private_key', re.compile(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----', re.S), b'[REDACTED_PRIVATE_KEY]'),
    ('provider_token', re.compile(rb'(?<![A-Za-z0-9_])(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|(?:AKIA|ASIA)[0-9A-Z]{16}|xox[bpars]-[0-9A-Za-z-]{20,})'), b'REDACTED_CREDENTIAL'),
    ('bearer', re.compile(rb'(?i)(Bearer\s+)[A-Za-z0-9._~+/-]{20,}'), rb'\1REDACTED_CREDENTIAL'),
    ('basic', re.compile(rb'(?i)(Basic\s+)[A-Za-z0-9+/=]{20,}'), rb'\1REDACTED_CREDENTIAL'),
    ('url_userinfo', re.compile(rb'(https?://)[^\s/\x22\x27<>]{1,150}:[^\s/\x22\x27<>]{1,200}@'), rb'\1REDACTED:REDACTED@'),
    ('literal_credential', re.compile(rb'(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|oauth[_-]?token|hf[_-]?token|password|passwd|client[_-]?secret|secret[_-]?key|cookie|set-cookie)\b[\x22\x27]?\s*[:=]\s*[\x22\x27])(?!REDACTED_CREDENTIAL)([^\x22\x27\r\n]{12,})([\x22\x27])'), rb'\1REDACTED_CREDENTIAL\3'),
]


def candidates(data):
    # Necessary literal markers are checked with C-level bytes search first.
    # This is an optimization, not a weaker credential rule: a regex match
    # cannot exist when all of its required literal prefixes are absent.
    result = set()
    if b'PRIVATE KEY-----' in data:
        result.add('private_key')
    if any(x in data for x in (b'sk-', b'ghp_', b'gho_', b'ghu_', b'ghs_', b'ghr_',
                              b'github_pat_', b'hf_', b'AIza', b'AKIA', b'ASIA',
                              b'xoxb-', b'xoxo-', b'xoxa-', b'xoxp-', b'xoxr-', b'xoxs-')):
        result.add('provider_token')
    lower = data.lower()
    if b'bearer' in lower:
        result.add('bearer')
    if b'basic' in lower:
        result.add('basic')
    if b'http://' in data or b'https://' in data:
        result.add('url_userinfo')
    literal_names = (b'api_key', b'api-key', b'apikey', b'access_token', b'access-token',
                     b'accesstoken', b'auth_token', b'auth-token', b'authtoken',
                     b'oauth_token', b'oauth-token', b'oauthtoken', b'hf_token',
                     b'hf-token', b'hftoken', b'password', b'passwd', b'client_secret',
                     b'client-secret', b'clientsecret', b'secret_key', b'secret-key',
                     b'secretkey', b'cookie')
    if any(x in lower for x in literal_names):
        result.add('literal_credential')
    return result


def clean(data):
    findings = []
    possible = candidates(data)
    for kind, pattern, replacement in RULES:
        if kind not in possible:
            continue
        data, n = pattern.subn(replacement, data)
        if n:
            findings.append({'kind': kind, 'count': n})
    return data, findings


def assert_clean(data):
    # The replacement strings deliberately do not match a provider prefix.
    possible = candidates(data)
    for kind, pattern, replacement in RULES:
        if kind not in possible:
            continue
        if kind == 'url_userinfo':
            check = data.replace(b'https://REDACTED:REDACTED@', b'https://')
            check = check.replace(b'http://REDACTED:REDACTED@', b'http://')
        else:
            check = data
        if pattern.search(check):
            raise ValueError('Unredacted credential pattern: ' + kind)
