from datetime import timedelta
from project.modules.base import Module
from project.helpers.embeds import *
from project.helpers.Cache import ArrayCache
from project import bot_config
from project.helpers.translator import translate
from Levenshtein import distance
from guilded import MemberJoinEvent, ChatMessage

import random
import re

class RaidUser:
    def __init__(self, id: str, name: str, avatar: str, created: datetime):
        self.id = id
        self.name = name
        self.avatar = avatar
        self.created = created

        self.raid_score = 0

def split_name(name: str):
    nameWords = name.split()
    res = []
    for word in nameWords:
        for item in re.split(r'(\d+)', word):
            res.append(item)
    return set(res)

def count_nondecimal(name: str):
    return len(re.sub(r'\d+', '', name))

def strip_numbers(name: str):
    return re.sub(r'\d+', '', name)

def calc_raid_scores(users: list):
    upper_user_limit = int(len(users) / 3)
    age_upper_limit = 60 * 60 * 24 * 2
    for user in users:
        user: RaidUser
        similar = 0
        similar_dist = 0
        for otherUser in users:
            otherUser: RaidUser
            if otherUser == user: continue
            cutoff = int(count_nondecimal(user.name) / 2)
            dist = distance(strip_numbers(user.name), strip_numbers(otherUser.name))
            if dist <= cutoff:
                similar += 1
                similar_dist += 1
            if similar == upper_user_limit:
                break
        age = (datetime.now() - user.created).total_seconds()
        similarity_score = (min(similar, upper_user_limit) / upper_user_limit) * 2
        avatar_score = user.avatar == None and 1 or 0
        age_score = 1 - (min(age, age_upper_limit) / age_upper_limit)
        user.raid_score = ((similarity_score + avatar_score + age_score) / 4) * 100

        #print(f'{user.name} - {user.raid_score} ({similarity_score} <{similar_dist}> : {avatar_score} : {age_score})')

def load_test_data():
    from project.helpers.raidguard_test_data import raidguard_test_data

    return [
        RaidUser(user['id'], user['name'], user.get('profilePicture', None), datetime.now() - timedelta(days=random.randrange(1, 5)))
            for user in raidguard_test_data
    ]

class RaidGuardModule(Module):
    name = 'RaidGuard'

    def initialize(self):
        bot = self.bot

        # TODO: Implement