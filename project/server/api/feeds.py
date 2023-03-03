from datetime import datetime
import re
from time import mktime
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import BotAPI, app, db
from project.server.api.auth import get_user_auth
from project.server.models import FeedData, Guild, GuildChannelConfig, GuildUser
from project.helpers.webhooks import post_webhook
from guilded import Embed, Colour
from guilded.embed import EmptyEmbed
from markdownify import markdownify
from werkzeug.exceptions import BadRequest

import feedparser

feeds_blueprint = Blueprint('feeds', __name__)

async def send_feed(server_id: str, channel_id: str, entry: dict):
    timestamp = entry.get('published_parsed', entry.get('created_parsed'))
    em = Embed(
        title=entry['title'],
        url=entry['link'],
        timestamp=datetime.fromtimestamp(mktime(timestamp)) if timestamp != None else None,
        description=markdownify(entry.get('summary', 'No summary provided.')),
        colour=Colour.gilded()
    ) \
        .set_author(
            name=entry.get('author', EmptyEmbed),
            url=entry.get('author_detail', {}).get('href', EmptyEmbed)
        )
    if entry.get('image', {}).get('href'):
        em = em.set_image(
            url=entry['image']['href']
        )
    elif entry.get('media_thumbnail', {}).get('url'):
        em = em.set_image(
            url=entry['media_thumbnai']['url']
        )

    try:
        return await post_webhook(server_id, channel_id, 
            embeds=[
                em
            ],
            username='Server Guard',
            avatar_url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'
        )
    except Exception as e:
        print(f'Failed to send feed update to {server_id}/{channel_id}: {str(e)}')

class FeedDataConfig(MethodView):
    """ Resource for getting and alter feed datas """
    async def get(self):
        auth = get_user_auth()

        if auth != 'm6YxwpQd':
            return 'Forbidden.', 403

        return jsonify({
            'feedDatas': [{
                'id': data.id,
                'url': data.url,
                'name': data.name,
                'blur_hash': data.blur_hash,
            } for data in FeedData.query.all()]
        }), 200
    async def post(self):
        auth = get_user_auth()

        if auth != 'm6YxwpQd':
            return 'Forbidden.', 403
        
        post_data = request.get_json()

        try:
            feedData: FeedData = FeedData(post_data['name'], post_data['url'], post_data['blur_hash'])
        except:
            return 'Bad Request', 400
        db.session.add(feedData)
        db.session.commit()

        return jsonify({
            'id': feedData.id
        }), 200
    async def patch(self, feed_id: str):
        auth = get_user_auth()

        if auth != 'm6YxwpQd':
            return 'Forbidden.', 403
        
        post_data: dict = request.get_json()

        feedData: FeedData = FeedData.query \
            .filter(FeedData.id == feed_id) \
            .first()
        
        if feedData == None:
            return 'Not Found', 404
        
        if post_data.get('name'):
            feedData.name = post_data['name']
        if post_data.get('url'):
            feedData.url = post_data['url']
        if post_data.get('blur_hash'):
            feedData.blur_hash = post_data['blur_hash']
        db.session.add(feedData)
        db.session.commit()
        return 'Success', 200
    async def delete(self, feed_id: str):
        auth = get_user_auth()

        if auth != 'm6YxwpQd':
            return 'Forbidden.', 403
        
        feedData: FeedData = FeedData.query \
            .filter(FeedData.id == feed_id) \
            .first()
        
        if feedData == None:
            return 'Not Found', 404
        
        db.session.delete(feedData)
        db.session.commit()
        return 'Deleted', 204

def parseURL(feedURL: str, url: str):
    custom = 'custom://'
    customName = None
    if url == None:
        raise BadRequest
    urlType = feedURL[len(custom):]
    if urlType == 'steam':
        match = re.search(r'store\.steampowered\.com/app/(\d+)/(\w*)', url)
        if match != None:
            match: re.Match
            url = f'https://steamcommunity.com/games/{match.group(1)}/rss/'
            if len(match.groups()) > 1:
                customName = f'Steam Game <{match.group(2)}>'
        else:
            raise BadRequest
    elif urlType == 'rss':
        rss: feedparser.FeedParserDict = feedparser.parse(url)
        if rss.get('bozo', 0) == 1:
            raise BadRequest
        customName = rss.get('feed', {}).get('title')
    else:
        raise BadRequest
    return url, customName

class FeedConfig(MethodView):
    """ Resource for getting and altering guild RSS feeds """
    async def get(self, guild_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            feeds = GuildChannelConfig.query \
                .filter(GuildChannelConfig.guild_id == guild_id) \
                .filter(GuildChannelConfig.type == 'feed') \
                .all()
            
            return jsonify({
                'feeds': [{
                    'id': feed.unique_id,
                    'channel': feed.channel_id,
                    'feed_id': feed.value['id'],
                    'url': feed.value.get('url'),
                    'name': feed.value.get('name'),
                } for feed in feeds],
                'feedDatas': [{
                    'id': data.id,
                    'url': data.url,
                    'name': data.name,
                    'blur_hash': data.blur_hash,
                } for data in FeedData.query.all()]
            }), 200
        else:
            return 'Forbidden', 403
    async def post(self, guild_id: str, channel_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            post_data: dict = request.get_json()
            feed_id = post_data['id']
            url = post_data.get('url')

            feedData: FeedData = FeedData.query \
                .filter(FeedData.id == feed_id) \
                .first()
            
            if feedData == None:
                return 'Bad Request', 400
            
            custom = 'custom://'
            if feedData.url.startswith(custom):
                if url == None:
                    return 'Bad Request', 400
                url, customName = parseURL(feedData.url, url)
                if customName:
                    feed = GuildChannelConfig(guild_id, channel_id, 'feed', {
                        'id': feed_id,
                        'url': url,
                        'name': customName
                    })
                else:
                    feed = GuildChannelConfig(guild_id, channel_id, 'feed', {
                        'id': feed_id,
                        'url': url
                    })
            else:
                feed = GuildChannelConfig(guild_id, channel_id, 'feed', {
                    'id': feed_id
                })
            db.session.add(feed)
            db.session.commit()

            return jsonify({
                'id': feed.unique_id,
                'value': feed.value
            }), 200
    async def patch(self, guild_id: str, feed_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            post_data: dict = request.get_json()
            feed: GuildChannelConfig = GuildChannelConfig.query \
                .filter(GuildChannelConfig.guild_id == guild_id) \
                .filter(GuildChannelConfig.type == 'feed') \
                .filter(GuildChannelConfig.unique_id == feed_id) \
                .first()
            
            feedData: FeedData = FeedData.query \
                .filter(FeedData.id == feed.value['id']) \
                .first()
            
            if feed != None:
                if feed.value.get('url') != None:
                    if post_data.get('url') == None:
                        return 'Bad Request', 400
                    url, customName = parseURL(feedData.url, post_data['url'])
                    feed.value['url'] = url
                    if customName != None:
                        feed.value['name'] = customName
                    db.session.add(feed)
                    db.session.commit()

                    return jsonify({
                        'url': url,
                        'name': customName
                    }), 200
                else:
                    return 'Bad Request', 400
            else:
                return 'Not Found', 404
        else:
            return 'Forbidden', 403
    async def delete(self, guild_id: str, feed_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            feed: GuildChannelConfig = GuildChannelConfig.query \
                .filter(GuildChannelConfig.guild_id == guild_id) \
                .filter(GuildChannelConfig.type == 'feed') \
                .filter(GuildChannelConfig.unique_id == feed_id) \
                .first()
            
            if feed != None:
                db.session.delete(feed)
                db.session.commit()

                return "Removed", 204
            else:
                return "Not Found", 404

class CheckFeeds(MethodView):
    """ Resource for checking guild RSS feeds """
    async def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        checked_feeds = {}

        feeds = GuildChannelConfig.query.filter(
            GuildChannelConfig.type == 'feed'
        ) \
            .paginate(per_page=50)
        for _ in feeds.iter_pages():
            contents = feeds.items
            for feed in contents:
                feed: GuildChannelConfig
                result: feedparser.FeedParserDict
                if feed.value.get('url'):
                    # This item is a custom RSS feed from a more flexible feed item
                    result = checked_feeds.get(feed.value['url'])
                    if result == None:
                        result = feedparser.parse(feed.value['url'])
                        checked_feeds[feed.value['url']] = result
                else:
                    # It's a normal feed item
                    result = checked_feeds.get(feed.value['id'])
                    if result == None:
                        feedData: FeedData = FeedData.query.filter(
                            FeedData.id == feed.value['id']
                        ).first()
                        if feedData != None:
                            result = feedparser.parse(feedData.url)
                            checked_feeds[feed.value['id']] = result
                if result != None:
                    knownIDs = feed.value.get('known', [])
                    newKnown = []
                    for item in result['entries']:
                        if not item['id'] in knownIDs:
                            await send_feed(feed.guild_id, feed.channel_id, item)
                        newKnown.append(item['id'])
                    feed.value['known'] = newKnown
                    db.session.add(feed)
                    db.session.commit()
        return 'Success', 200

feeds_blueprint.add_url_rule('/feeds/check', view_func=CheckFeeds.as_view('checkfeeds'))
feeds_blueprint.add_url_rule('/feeds/<guild_id>', view_func=FeedConfig.as_view('getfeeds'))
feeds_blueprint.add_url_rule('/feeds/<guild_id>/<feed_id>', view_func=FeedConfig.as_view('alterfeeds'))
feeds_blueprint.add_url_rule('/feeds/<guild_id>/<channel_id>/new', view_func=FeedConfig.as_view('createfeeds'))
feeds_blueprint.add_url_rule('/feeds/data/<feed_id>', view_func=FeedDataConfig.as_view('feeddatas'))
feeds_blueprint.add_url_rule('/feeds/data', view_func=FeedDataConfig.as_view('alterfeeddatas'))