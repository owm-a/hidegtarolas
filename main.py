import os
import io
import zipfile
import requests
import pandas as pd

from datetime import datetime
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2


# ===========================================================
# BEÁLLÍTÁSOK
# ===========================================================

API_KEY = os.environ["BKK_API_KEY"]

GTFS_URL = (
    "https://go.bkk.hu/api/static/v1/public-gtfs/"
    "budapest_gtfs.zip"
)

VEHICLE_POSITIONS_URL = (
    "https://go.bkk.hu/api/query/v1/ws/"
    "gtfs-rt/full/VehiclePositions.pb"
)


print("Program elindult.")
