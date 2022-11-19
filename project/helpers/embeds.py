from datetime import datetime
from guilded import Embed, Colour, Member
from project.helpers.images import *

def EMBED_DENIED(**kwargs):
    """Represents a Discord embed.

    .. container:: operations

        .. describe:: len(x)

            Returns the total size of the embed.
            Useful for checking if it's within the 6000 character limit.

    Certain properties return an ``EmbedProxy``, a type
    that acts similar to a regular :class:`dict` except using dotted access,
    e.g. ``embed.author.icon_url``. If the attribute
    is invalid or empty, then a special sentinel value is returned,
    :attr:`Embed.Empty`.

    URL parameters (both as text and for images) accept any string, even those
    that are not a valid URI. If an ``attachment://`` URI is passed to an image
    parameter then it will be handled for you.

    For ease of use, all parameters that expect a :class:`str` are implicitly
    casted to :class:`str` for you.

    Attributes
    -----------
    title: :class:`str`
        The title of the embed.
        This can be set during initialisation.
    description: :class:`str`
        The description of the embed.
        This can be set during initialisation.
    url: :class:`str`
        The URL of the embed.
        This can be set during initialisation.
    timestamp: :class:`datetime.datetime`
        The timestamp of the embed content. This could be a naive or aware datetime.
    colour: Union[:class:`Colour`, :class:`int`]
        The colour code of the embed. Aliased to ``color`` as well.
        This can be set during initialisation.
    Empty
        A special sentinel value used by ``EmbedProxy`` and this class
        to denote that the value or attribute is empty.
    """
    em = Embed(**kwargs)
    em.set_thumbnail(url=IMAGE_DENIED)
    return em

EMBED_DENIED_MOD = EMBED_DENIED(
    title='Forbidden',
    description='You must be a moderator to do that!',
    colour=Colour.red()
)

EMBED_DENIED_ADMIN = EMBED_DENIED(
    title='Forbidden',
    description='You must be an administrator to do that!',
    colour=Colour.red()
)

def EMBED_COMMAND_ERROR(err: str = 'An unexpected error occurred'):
    em = Embed(
        title='An Error Occurred',
        description=f'An error occurred and the command could not be executed: {err}',
        colour=Colour.orange()
    )
    em.set_thumbnail(url=IMAGE_DENIED)
    return em

def EMBED_SUCCESS(msg: str = 'Successfully executed command'):
    em = Embed(
        title='Success',
        description=msg,
        colour=Colour.green()
    )
    #em.set_thumbnail(url=IMAGE_GIL_THUMBS_UP)
    return em

def EMBED_NEEDS_PREMIUM(tier: int):
    em = Embed(
        title='Premium-Only Feature',
        description=f'This feature requires Premium Tier {tier}! This server does not have this Premium tier. To get Premium for a server, the server\'s owner must purchase it [here](https://www.guilded.gg/server-guard/subscriptions)',
        colour=Colour.gold()
    )
    em.set_thumbnail(url=IMAGE_SUB_GOLD)
    return em

def EMBED_FILTERED(member: Member, reason: str):
    return EMBED_DENIED(
        title='Message filtered',
        description=f'{member.mention}, your message has been removed by one of this server\'s filters for "{reason}". Please do not do this again or moderation actions may be taken against you.',
        colour=Colour.orange()
    )

def EMBED_TIMESTAMP_NOW(**kwargs):
    """Represents a Discord embed.

    .. container:: operations

        .. describe:: len(x)

            Returns the total size of the embed.
            Useful for checking if it's within the 6000 character limit.

    Certain properties return an ``EmbedProxy``, a type
    that acts similar to a regular :class:`dict` except using dotted access,
    e.g. ``embed.author.icon_url``. If the attribute
    is invalid or empty, then a special sentinel value is returned,
    :attr:`Embed.Empty`.

    URL parameters (both as text and for images) accept any string, even those
    that are not a valid URI. If an ``attachment://`` URI is passed to an image
    parameter then it will be handled for you.

    For ease of use, all parameters that expect a :class:`str` are implicitly
    casted to :class:`str` for you.

    Attributes
    -----------
    title: :class:`str`
        The title of the embed.
        This can be set during initialisation.
    description: :class:`str`
        The description of the embed.
        This can be set during initialisation.
    url: :class:`str`
        The URL of the embed.
        This can be set during initialisation.
    timestamp: :class:`datetime.datetime`
        The timestamp of the embed content. This could be a naive or aware datetime.
    colour: Union[:class:`Colour`, :class:`int`]
        The colour code of the embed. Aliased to ``color`` as well.
        This can be set during initialisation.
    Empty
        A special sentinel value used by ``EmbedProxy`` and this class
        to denote that the value or attribute is empty.
    """
    em = Embed(
        timestamp=datetime.now(),
        **kwargs
    )
    return em