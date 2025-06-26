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
    print("Starting Aquarea client...")
    async with aiohttp.ClientSession() as session:
        client = Client(
            username="username@gmail.com",
            password="your_password",
            session=session,
            device_direct=True,
            refresh_login=True,
            environment=AquareaEnvironment.PRODUCTION,
        )

        # The library is designed to retrieve a device object and interact with it:
        print("Fetching devices...")
        devices = await client.get_devices()
        print(f"Devices fetched: {devices}")

        # Picking the first device associated with the account:
        device_info = devices[0]

        device = await client.get_device(
            device_info=device_info, consumption_refresh_interval=timedelta(minutes=1)
        )

        # Or the device can also be retrieved by its long id if we know it:
        #device = await client.get_device(
        #    device_id="LONG ID", consumption_refresh_interval=timedelta(minutes=1)
        #)

        # Then we can interact with the device:
        #await device.set_mode(UpdateOperationMode.HEAT)

        # The device can automatically refresh its data:
        #await device.refresh_data()

if __name__ == "__main__":
    asyncio.run(main())
