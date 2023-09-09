from project import BotAPI

async def get_user_premium_status(user_id):
    with BotAPI() as bot_api:
        try:
            roles = await bot_api.get_member_roles('aE9Zg6Kj', user_id)
        except Exception:
            roles = None
        if roles is not None:
            roles = roles['roleIds']
        else:
            roles = []

        if 32612283 in roles:
            cached = 3
        elif 32612284 in roles:
            cached = 2
        elif 32612285 in roles:
            cached = 1
        else:
            cached = 0

        return cached