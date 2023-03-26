

class Logger:
    def __init__(self, level='debug'):
        self.level = level

    def DebugLog(self, *args):
        if self.level == 'debug':
            print(*args)

    def TraceLog(self, *args):
        if self.level == 'trace':
            print(*args)

    def setDebugLevel(self, level):
        self.level = level.lower()