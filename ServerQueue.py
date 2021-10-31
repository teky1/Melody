class ServerQueue:
    def __init__(self, server):
        self.server = server
        self.is_playing = False
        self.current_queue_number = None
        self.queue = []
        self.channel = None
        self.active_text_channel = None  # the text channel that the bot was most recently talked to in
        self.looping = False

    def current_song(self):
        return self.queue[self.current_queue_number]