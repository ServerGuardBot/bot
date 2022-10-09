from threading import Timer

import time

class Cache:
    def __init__(self, expires_after: int = 300):
        self.__cache = {}
        self.__expire_after = expires_after
        self.__timer = Timer(1, self.__check)
        
        self.__timer.start()
    
    def __del__(self):
        self.__cache = {}
        self.__timer.cancel()
        del self.__timer
    
    def __check(self):
        for key in list(self.__cache.keys()):
            if time.time() - self.__cache[key][0] > self.__expire_after:
                del self.__cache[key]
        self.__timer = Timer(1, self.__check)
        self.__timer.start()
    
    def get(self, key: str):
        if key in self.__cache:
            return self.__cache[key][1]
        return None
    
    def set(self, key: str, value):
        self.__cache[key] = [time.time(), value]
    
    def remove(self, key: str):
        if key in self.__cache:
            del self.__cache[key]