from evileye.api.core.journal_adapters_factory import _adapter_params, create_event_journal_adapters


def test_deployment_top_level_adapter_config_is_supported():
    config = {'database_adapters': {'DatabaseAdapterZoneEvents': {'table_name': 'zone_events'}}}
    adapters = create_event_journal_adapters(None, config)
    assert any(adapter.table_name == 'zone_events' for adapter in adapters)


def test_nested_adapter_config_overrides_legacy_entries():
    assert _adapter_params({'database_adapters': {'x': 1, 'y': 2},
                            'database': {'adapters': {'x': 3}}}) == {'x': 3, 'y': 2}
