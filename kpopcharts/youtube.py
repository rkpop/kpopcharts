#!/usr/bin/env python3
#
# Copyright (C) 2015 by NewbieSone <newbiesone@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# stdlib
import contextlib
import difflib

# third-party
from apiclient.discovery import build
from apiclient.errors import HttpError

class YouTubeError(Exception):
    pass

class _YouTube():
    _api_key = None

class Video(_YouTube):
    def __init__(self, pattern, api_key=None):
        self._pattern = pattern

        if api_key is not None:
            self._api_key = api_key

        if self._api_key is None:
            raise YouTubeError('No API key set.')

        self.url = self._find()

    def _find(self):
        try:
            youtube = build('youtube', 'v3', developerKey=self._api_key)

            response = youtube.search().list(q=self._pattern, part='id,snippet', type='video',
                safeSearch='none', regionCode='US', maxResults=10).execute()

            for result in response.get("items", []):
                match = None
                snippet = result['snippet']
                sim = difflib.SequenceMatcher(None, self._pattern, snippet['title']).ratio()

                if sim > 0.6:
                    match = result['id']['videoId']

                channel = youtube.channels().list(id=snippet['channelId'],
                    part='statistics', maxResults=1).execute().get("items", [])[0]
                subscribers = channel['statistics']['subscriberCount']

                if int(subscribers) > 100000 and not 'teaser' in snippet['title'].lower():
                    match = result['id']['videoId']

                return 'https://youtu.be/{0}'.format(match) if match else ''
        except Exception:
            return ''

class Session():
    def __init__(self, api_key):
        self._api_key = api_key

    def __enter__(self):
        self._old_api_key = _YouTube._api_key
        _YouTube._api_key = self._api_key

    def __exit__(self, *args):
        _YouTube._api_key = self._old_api_key
