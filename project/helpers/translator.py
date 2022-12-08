LOCALIZATION_BASE = 'https://localization.serverguard.xyz/'

import asyncio
import requests
import re

from threading import Timer

languages: dict = {}
loadedLanguages: dict = {}
loaded = False

async def translate(locale, key, values: dict):
    while not loaded:
        await asyncio.sleep(.1)
    lang = loadedLanguages.get(locale, loadedLanguages.get('en', {}))
    translation = lang.get(key, loadedLanguages.get('en', {}).get(key))
    if translation:
        res = translation
        if values:
            for index in values.keys():
                item = values[index]
                res = re.sub(rf'{{\s*{index}\s*}}', item)
        return res
    else:
        raise Exception(f'The key "{key}" does not exist in locale "{locale}" or the "en" locale')

def loadLanguages():
    global languages
    global loadedLanguages
    lang_req = requests.get(LOCALIZATION_BASE + 'languages.json')

    if lang_req.status_code == 200:
        try:
            languages = lang_req.json()
        except Exception as e:
            print(f'WARNING: languages.json file contains invalid JSON, "{str(e)}"')
    
    for locale in languages.keys():
        req = requests.get(LOCALIZATION_BASE + f'/bot/{locale}.json')
        if req.status_code == 200:
            try:
                loadedLanguages[locale] = req.json()
            except Exception as e:
                print(f'WARNING: bot/{locale}.json file contains invalid JSON, "{str(e)}"')
        else:
            print(f'WARNING: bot/{locale}.json file missing')

def reloadLangs():
    global timer
    loadLanguages()
    timer = Timer(10, reloadLangs)
    timer.start()

loadLanguages()

timer = Timer(10, reloadLangs)
timer.start()