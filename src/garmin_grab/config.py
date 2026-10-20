"""Constants shared by the grabber modules."""
import os

TOKENSTORE = os.path.expanduser(os.getenv("GARMINTOKENS", "~/.garminconnect"))
PAGE = 100
SAMPLE_EVERY_S = 10          # stream resolution stored in runs.json
NO_GPS_TYPES = ("treadmill", "indoor", "virtual")
RHR_CHUNK_DAYS = 364         # get_rhr_daily returns up to ~1 year per request
RHR_REFRESH_DAYS = 7         # re-fetch the last week: today's value settles later
