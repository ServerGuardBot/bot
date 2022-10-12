from project.modules.base import Module
from project import bot_config
from guilded.ext import commands
from guilded import Embed

class GeneralModule(Module):
    name = "General"

    def initialize(self):
        bot = self.bot

        # Register help command
        @bot.command(name='commands')
        async def commands_(ctx: commands.Context):
            print('Received commands cmd', flush=True)
            await ctx.reply(embed=Embed(
                title='Commands',
                description=
        '''/verify - start the verification process
        /evaluate `<user>` - Moderator+, shows an evaluation of a user
        /config - Administrator, configure the bot's settings. Use /config help for more information
        /bypass `<user>` - Moderator+, allows a user to bypass verification
        /unbypass `<user>` - Moderator+, revokes a user's verification bypass
        /commands - brings up this help text
        '''
            ))
