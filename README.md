Aioaquarea
===================

Asynchronous library to control Panasonic Aquarea devices

## Requirements

This library requires:

- Python >= 3.9
- asyncio
- aiohttp

## Usage
The library supports the production environment of the Panasonic Aquarea Smart Cloud API and also the Demo environment. One of the main usages of this library is to integrate the Panasonic Aquarea Smart Cloud API with Home Assistant via [home-assistant-aquarea](https://github.com/cjaliaga/home-assistant-aquarea)

Here is a simple example of how to use the library via getting a device object to interact with it:

```python
from aioaquarea import (
    Client,
    AquareaEnvironment,
    UpdateOperationMode
)

import aiohttp
import asyncio
import logging
from datetime import timedelta

async def main():
    async with aiohttp.ClientSession() as session:
        client = Client(
            username="USERNAME",
            password="PASSWORD",
            session=session,
            device_direct=True,
            refresh_login=True,
            environment=AquareaEnvironment.PRODUCTION,
        )

        # The library is designed to retrieve a device object and interact with it:
        devices = await client.get_devices(include_long_id=True)

        # Picking the first device associated with the account:
        device_info = devices[0]

        device = await client.get_device(
            device_info=device_info, consumption_refresh_interval=timedelta(minutes=1)
        )

        # Or the device can also be retrieved by its long id if we know it:
        device = await client.get_device(
            device_id="LONG ID", consumption_refresh_interval=timedelta(minutes=1)
        )

        # Then we can interact with the device:
        await device.set_mode(UpdateOperationMode.HEAT)

        # The device can automatically refresh its data:
        await device.refresh_data()
```

## Acknowledgements

Big thanks to [ronhks](https://github.com/ronhks) for his awesome work on the [Panasonic Aquaera Smart Cloud integration with MQTT](https://github.com/ronhks/panasonic-aquarea-smart-cloud-mqtt).