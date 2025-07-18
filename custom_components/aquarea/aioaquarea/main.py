import aiohttp
import asyncio
import logging
from datetime import timedelta
import os

async def main():
    print("Starting Aquarea client...")
    async with aiohttp.ClientSession() as session:
        client = Client(
            username=os.environ["USER_NAME"],
            password=os.environ["PASSWORD"],
            session=session,
            device_direct=True,
            refresh_login=True,
            environment=AquareaEnvironment.PRODUCTION,
        )

        # The library is designed to retrieve a device object and interact with it:
        devices = await client.get_devices()

        # Picking the first device associated with the account:
        device_info = devices[0]

        device = await client.get_device(
            device_info=device_info, consumption_refresh_interval=timedelta(minutes=1)
        )

        # Then we can interact with the device:
        await device.set_temperature(18, 1)

        # The device can automatically refresh its data:
        #await device.refresh_data()

if __name__ == "__main__":
    asyncio.run(main())
