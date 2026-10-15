# SPDX-License-Identifier: GPL-3.0-only
"""Import legacy build artwork without teaching the shared host native formats."""
from collections.abc import Mapping
from stodex.sdk.assets import reference


def normalize_assets(value):
    if isinstance(value, (tuple, list)):
        return [normalize_assets(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    result = {key: normalize_assets(item) for key, item in value.items()}
    icon = result.get('icon')
    if isinstance(icon, Mapping) and set(icon) == {'archive', 'member'}:
        result['icon'] = reference(['images', 'hogg', icon['archive'], icon['member']])
    elif 'icon' not in result and isinstance(result.get('icon_token'), str) and result['icon_token']:
        result['icon'] = reference(['images', 'native', result['icon_token']])
    return result
