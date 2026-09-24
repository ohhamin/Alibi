from app.game_service import _as_dict, _as_list


def test_as_dict_is_safe():
    assert _as_dict({'round': 1}) == {'round': 1}
    assert _as_dict(None) == {}


def test_as_list_is_safe():
    assert _as_list(['fact']) == ['fact']
    assert _as_list(None) == []
