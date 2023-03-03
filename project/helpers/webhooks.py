from json import JSONDecoder, JSONEncoder
from project import BotAPI, db
from project.server.models import Guild
from guilded import Webhook, NotFound

async def post_webhook(guild_id: str, channel_id: str, *args, **kwargs):
    """|coro|

    Sends a message or create a list item using this webhook.

    .. warning::

        If this webhook is in a :class:`ListChannel`, this method will
        return a :class:`ListItem` instead of a :class:`WebhookMessage`.

    The content must be a type that can convert to a string through ``str(content)``.

    To upload a single file, the ``file`` parameter should be used with a
    single :class:`File` object.

    If the ``embed`` parameter is provided, it must be of type :class:`Embed` and
    it must be a rich embed type. You cannot mix the ``embed`` parameter with the
    ``embeds`` parameter, which must be a :class:`list` of :class:`Embed` objects to send.

    Parameters
    ------------
    content: :class:`str`
        The :attr:`~WebhookMessage.content` of the message to send,
        or the :attr:`~ListItem.message` of the list item to create.
    username: :class:`str`
        A custom username to use with this message instead of the
        webhook's own username.

        .. versionadded:: 1.4
    avatar_url: :class:`str`
        A custom avatar URL to use with this message instead of the
        webhook's own avatar.
        This is explicitly cast to ``str`` if it is not already.

        .. versionadded:: 1.4
    file: :class:`File`
        The file to upload. This cannot be mixed with ``files`` parameter.
    files: List[:class:`File`]
        A list of files to send. This cannot be mixed with the
        ``file`` parameter.
    embed: :class:`Embed`
        The rich embed for the content to send. This cannot be mixed with
        ``embeds`` parameter.
    embeds: List[:class:`Embed`]
        A list of embeds to send. Maximum of 10. This cannot
        be mixed with the ``embed`` parameter.

    Returns
    ---------
    Union[:class:`WebhookMessage`, :class:`ListItem`]
        If this webhook is in a :class:`ChatChannel`, the :class:`WebhookMessage` that was sent.
        Otherwise, the :class:`ListItem` that was created.

    Raises
    --------
    HTTPException
        Executing the webhook failed.
    NotFound
        This webhook was not found.
    Forbidden
        The token for the webhook is incorrect.
    TypeError
        You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
    ValueError
        The length of ``embeds`` was invalid or there was no token
        associated with this webhook.
    """

    with BotAPI() as bot_api:
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild != None:
            webhooks = guild.config.get('__webhooks')
            if webhooks == None:
                webhooks = {}
                guild.config['__webhooks'] = webhooks
            webhook_data = webhooks.get(channel_id)
            if webhook_data == None:
                data: dict = (await bot_api.create_webhook(
                    server_id=guild_id,
                    name='Server Guard Webhook',
                    channel_id=channel_id
                ))['webhook']
                webhook = Webhook(state=bot_api, data=data, session=bot_api.session)
                webhook_data = data
                webhooks[channel_id] = data
                db.session.add(guild)
                db.session.commit()
            else:
                webhook = Webhook(state=bot_api, data=webhook_data, session=bot_api.session)
            try:
                return await webhook.send(*args, **kwargs)
            except NotFound:
                # Fallback to deleting the webhook data and retrying this function in order to recreate the webhook
                del webhooks[channel_id]
                db.session.add(guild)
                db.session.commit()
                return await post_webhook(guild_id, channel_id, *args, **kwargs)
            except Exception:
                raise Exception