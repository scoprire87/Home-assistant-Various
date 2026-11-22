"""Config flow: connessione al datalogger + opzioni (notifiche, IA)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import ZcsClient, ZcsError
from .const import (
    AI_CONVERSATION,
    AI_HA_TEXT_AI,
    AI_NONE,
    AI_OPENAI,
    AI_PROVIDERS,
    AI_TASK,
    BAT_QTY,
    BAT_START,
    CONF_AI_API_KEY,
    CONF_AI_BASE_URL,
    CONF_AI_ENTITY,
    CONF_AI_MODEL,
    CONF_AI_PROVIDER,
    CONF_NOTIFY,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_SLAVE,
    CONF_SUNSET_OFFSET,
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_MODEL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DEFAULT_SUNSET_OFFSET,
    DOMAIN,
)


async def _test_connection(data: dict[str, Any]) -> None:
    client = ZcsClient(data[CONF_HOST], data[CONF_PORT], data[CONF_SERIAL], data[CONF_SLAVE])
    try:
        await client.read_input(BAT_START, BAT_QTY)
    finally:
        await client.close()


class ZcsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_SERIAL] = int(user_input[CONF_SERIAL])
            await self.async_set_unique_id(str(user_input[CONF_SERIAL]))
            self._abort_if_unique_id_configured()
            try:
                await _test_connection(user_input)
            except ZcsError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="ZCS Azzurro", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_SERIAL): str,
            vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): int,
            vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=5, max=300)),
        })
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ZcsOptionsFlow()


class ZcsOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        self._opts: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._opts = {**self.config_entry.options, **user_input}
            provider = user_input[CONF_AI_PROVIDER]
            if provider == AI_NONE:
                return self.async_create_entry(data=self._opts)
            return await getattr(self, f"async_step_{provider}")()

        opts = self.config_entry.options
        schema = vol.Schema({
            vol.Optional(CONF_NOTIFY, description={"suggested_value": opts.get(CONF_NOTIFY, "")}): str,
            vol.Required(CONF_SUNSET_OFFSET, default=opts.get(CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET)):
                vol.All(int, vol.Range(min=0, max=180)),
            vol.Required(CONF_AI_PROVIDER, default=opts.get(CONF_AI_PROVIDER, AI_NONE)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=AI_PROVIDERS, translation_key="ai_provider",
                                              mode=selector.SelectSelectorMode.LIST)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)

    async def _entity_step(self, step_id: str, sel, user_input) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._opts, **user_input})
        schema = vol.Schema({
            vol.Required(CONF_AI_ENTITY, description={"suggested_value": self._opts.get(CONF_AI_ENTITY)}): sel,
        })
        return self.async_show_form(step_id=step_id, data_schema=schema)

    async def async_step_ai_task(self, user_input=None) -> ConfigFlowResult:
        return await self._entity_step(AI_TASK, selector.EntitySelector(
            selector.EntitySelectorConfig(domain="ai_task")), user_input)

    async def async_step_ha_text_ai(self, user_input=None) -> ConfigFlowResult:
        return await self._entity_step(AI_HA_TEXT_AI, selector.EntitySelector(
            selector.EntitySelectorConfig(integration="ha_text_ai", domain="sensor")), user_input)

    async def async_step_conversation(self, user_input=None) -> ConfigFlowResult:
        return await self._entity_step(AI_CONVERSATION, selector.ConversationAgentSelector(
            selector.ConversationAgentSelectorConfig()), user_input)

    async def async_step_openai_compatibile(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._opts, **user_input})
        schema = vol.Schema({
            vol.Required(CONF_AI_BASE_URL, default=self._opts.get(CONF_AI_BASE_URL, DEFAULT_AI_BASE_URL)): str,
            vol.Required(CONF_AI_API_KEY, description={"suggested_value": self._opts.get(CONF_AI_API_KEY)}):
                selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Required(CONF_AI_MODEL, default=self._opts.get(CONF_AI_MODEL, DEFAULT_AI_MODEL)): str,
        })
        return self.async_show_form(step_id=AI_OPENAI, data_schema=schema)
