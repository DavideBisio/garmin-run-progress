"""Constants shared by the grabber modules."""
import os

TOKENSTORE = os.path.expanduser(os.getenv("GARMINTOKENS", "~/.garminconnect"))
PAGE = 100
SAMPLE_EVERY_S = 10          # stream resolution stored in runs.json
NO_GPS_TYPES = ("treadmill", "indoor", "virtual")
RHR_CHUNK_DAYS = 364         # get_rhr_daily returns up to ~1 year per request
RHR_REFRESH_DAYS = 7         # re-fetch the last week: today's value settles later
HRV_CHUNK_DAYS = 28          # get_hrv_data_range: days per request (Garmin's limit is unconfirmed)
WELLNESS_REFRESH_DAYS = 7    # HRV and readiness: re-fetch the last week, as resting HR
READINESS_FIRST_DAYS = 60    # get_training_readiness is one request a day: at most this many days
