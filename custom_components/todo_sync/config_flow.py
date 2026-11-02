"""Config flow: pick two to-do lists."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_LIST_A, CONF_LIST_B, DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LIST_A): EntitySelector(EntitySelectorConfig(domain="todo")),
        vol.Required(CONF_LIST_B): EntitySelector(EntitySelectorConfig(domain="todo")),
    }
)


class TodoSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            a, b = user_input[CONF_LIST_A], user_input[CONF_LIST_B]
            if a == b:
                errors["base"] = "same_list"
            else:
                await self.async_set_unique_id("|".join(sorted((a, b))))
                self._abort_if_unique_id_configured()
                name = lambda e: (st.name if (st := self.hass.states.get(e)) else e)  # noqa: E731
                return self.async_create_entry(title=f"{name(a)} ⇄ {name(b)}", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
