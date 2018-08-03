#!//usr/bin/env python3

import os
import time

DAYS_to_keep = 5
PATH="/var/www/html/rss/"

time_to_keep = DAYS_to_keep * 24 * 3600
dirents = os.listdir(PATH)
for ent in dirents:
    if (time.time() - os.path.getmtime(PATH + ent) > time_to_keep):
        if (os.path.isfile(PATH + ent)):
            os.remove(PATH + ent)
            