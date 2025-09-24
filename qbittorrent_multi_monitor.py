#!/usr/bin/env python3
"""
qBittorrent Multi-Instance Monitor

A monitoring application that connects to multiple qBittorrent instances
and automatically cleans torrent names by removing domain names and URLs
from torrent titles, folders, and filenames.

This module provides:
- Multi-instance qBittorrent monitoring
- Intelligent domain/URL extraction and removal
- File and folder renaming with conflict handling
- Robust error handling with exponential backoff
- Comprehensive logging
"""

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests  # pylint: disable=import-error
from requests.adapters import HTTPAdapter  # pylint: disable=import-error
from urllib3.util.retry import Retry  # pylint: disable=import-error

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/qbittorrent_monitor.log'),
        logging.StreamHandler()
    ]
)

class QBittorrentInstance:  # pylint: disable=too-many-instance-attributes
    """
    Represents a single qBittorrent instance with monitoring and management capabilities.

    This class handles connection, authentication, and operations for a single qBittorrent
    instance, including torrent renaming, file operations, and error handling with
    exponential backoff retry logic.

    Attributes:
        name (str): Friendly name for this instance
        base_url (str): Base URL for the qBittorrent Web API
        username (str): Authentication username
        password (str): Authentication password
        check_interval (int): Polling interval in seconds
        max_retries (int): Maximum retry attempts for operations
        retry_delay (int): Base delay between retries in seconds
        folder_retry_delay (int): Extended delay for folder operations
        connection_timeout (int): HTTP timeout in seconds
        session (requests.Session): HTTP session for persistent connections
        last_error_time (float): Timestamp of last error for backoff calculation
        error_count (int): Consecutive error count for exponential backoff
    """
    def __init__(self, name, url, username, password, check_interval=30,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 max_retries=5, retry_delay=10, folder_retry_delay=30,
                 connection_timeout=30):
        self.name = name
        self.base_url = url.rstrip('/')
        self.username = username
        self.password = password
        self.check_interval = int(check_interval)
        self.max_retries = int(max_retries)
        self.retry_delay = int(retry_delay)
        self.folder_retry_delay = int(folder_retry_delay)
        self.connection_timeout = int(connection_timeout)
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.last_error_time = None
        self.error_count = 0

    def login(self):
        """Login to qBittorrent Web UI"""
        try:
            login_data = {'username': self.username, 'password': self.password}
            response = self.session.post(
                f'{self.base_url}/api/v2/auth/login',
                data=login_data,
                timeout=(10, self.connection_timeout)
            )
            if response.text == 'Ok.':
                logging.info("[%s] Successfully logged in to qBittorrent", self.name)
                self.last_error_time = None
                self.error_count = 0
                return True
            logging.error("[%s] Failed to login to qBittorrent: %s", self.name, response.text)
            return False
        except requests.exceptions.ConnectTimeout:
            logging.error("[%s] Connection timeout when connecting to %s", self.name, self.base_url)
            self.handle_error()
            return False
        except requests.exceptions.ConnectionError as e:
            logging.error("[%s] Connection error when connecting to %s: %s",
                         self.name, self.base_url, e)
            self.handle_error()
            return False
        except requests.exceptions.Timeout as e:
            logging.error("[%s] Timeout when connecting to %s: %s", self.name, self.base_url, e)
            self.handle_error()
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
            logging.error("[%s] Unexpected error logging in: %s", self.name, e)
            self.handle_error()
            return False

    def handle_error(self):
        """Handle errors with exponential backoff"""
        self.error_count += 1
        self.last_error_time = time.time()

    def should_retry(self):
        """Check if we should retry after an error"""
        if self.last_error_time is None:
            return True
        # Exponential backoff: wait longer between retries
        # Max 5 minutes
        wait_time = min(300, 30 * (2 ** (self.error_count - 1)))
        return (time.time() - self.last_error_time) > wait_time

    def get_torrents(self):
        """Get list of all torrents"""
        try:
            response = self.session.get(
                f'{self.base_url}/api/v2/torrents/info',
                timeout=(10, self.connection_timeout)
            )
            if response.status_code == 200:
                return response.json()
            logging.error("[%s] Failed to get torrents: HTTP %s", self.name, response.status_code)
            return []
        except requests.exceptions.ConnectTimeout:
            logging.error("[%s] Connection timeout when fetching torrents from %s",
                         self.name, self.base_url)
            self.handle_error()
            return []
        except requests.exceptions.ConnectionError as e:
            logging.error("[%s] Connection error when fetching torrents from %s: %s",
                         self.name, self.base_url, e)
            self.handle_error()
            return []
        except requests.exceptions.Timeout as e:
            logging.error("[%s] Timeout when fetching torrents from %s: %s",
                         self.name, self.base_url, e)
            self.handle_error()
            return []
        except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
            logging.error("[%s] Error fetching torrents: %s", self.name, e)
            self.handle_error()
            return []

    def get_torrent_files(self, torrent_hash):
        """Get files in a torrent"""
        try:
            response = self.session.get(
                f'{self.base_url}/api/v2/torrents/files?hash={torrent_hash}',
                timeout=(10, self.connection_timeout)
            )
            if response.status_code == 200:
                return response.json()
            logging.error("[%s] Failed to get files for torrent %s: HTTP %s",
                         self.name, torrent_hash, response.status_code)
            return []
        except requests.exceptions.ConnectTimeout:
            logging.error("[%s] Connection timeout when fetching files for torrent %s",
                         self.name, torrent_hash)
            return []
        except requests.exceptions.ConnectionError as e:
            logging.error("[%s] Connection error when fetching files for torrent %s: %s",
                         self.name, torrent_hash, e)
            return []
        except requests.exceptions.Timeout as e:
            logging.error("[%s] Timeout when fetching files for torrent %s: %s",
                         self.name, torrent_hash, e)
            return []
        except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
            logging.error("[%s] Error fetching torrent files for %s: %s",
                         self.name, torrent_hash, e)
            return []

    def get_torrent_properties(self, torrent_hash):
        """Get torrent properties to check state"""
        try:
            response = self.session.get(
                f'{self.base_url}/api/v2/torrents/properties?hash={torrent_hash}',
                timeout=(10, self.connection_timeout)
            )
            if response.status_code == 200:
                return response.json()
            logging.debug("[%s] Could not get properties for torrent %s: HTTP %s",
                         self.name, torrent_hash, response.status_code)
            return None
        except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
            logging.debug("[%s] Error getting torrent properties for %s: %s",
                         self.name, torrent_hash, e)
            return None

    def pause_torrent(self, torrent_hash):
        """Pause a torrent"""
        try:
            normalized_hash = self._normalize_torrent_hash(torrent_hash)
            data = {'hashes': normalized_hash}
            url = f'{self.base_url}/api/v2/torrents/pause'
            logging.debug("[%s] Attempting to pause torrent %s (normalized: %s) using URL: %s", 
                         self.name, torrent_hash, normalized_hash, url)
            
            response = self.session.post(
                url,
                data=data,
                timeout=(10, self.connection_timeout)
            )
            
            logging.debug("[%s] Pause response: HTTP %s, Content: %s", 
                         self.name, response.status_code, response.text[:200])
            
            if response.status_code == 200:
                logging.info("[%s] Paused torrent %s", self.name, torrent_hash)
                return True
                
            # Handle different error codes
            if response.status_code == 404:
                logging.error("[%s] Torrent %s not found (HTTP 404). "
                             "It may have been removed or the hash is incorrect.", 
                             self.name, torrent_hash)
            else:
                logging.warning("[%s] Failed to pause torrent %s: HTTP %s - %s",
                               self.name, torrent_hash, response.status_code, response.text)
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("[%s] Error pausing torrent %s: %s", self.name, torrent_hash, e)
            return False

    def resume_torrent(self, torrent_hash):
        """Resume a torrent"""
        try:
            normalized_hash = self._normalize_torrent_hash(torrent_hash)
            data = {'hashes': normalized_hash}
            url = f'{self.base_url}/api/v2/torrents/resume'
            logging.debug("[%s] Attempting to resume torrent %s (normalized: %s) using URL: %s", 
                         self.name, torrent_hash, normalized_hash, url)
            
            response = self.session.post(
                url,
                data=data,
                timeout=(10, self.connection_timeout)
            )
            
            logging.debug("[%s] Resume response: HTTP %s, Content: %s", 
                         self.name, response.status_code, response.text[:200])
            
            if response.status_code == 200:
                logging.info("[%s] Resumed torrent %s", self.name, torrent_hash)
                return True
                
            # Handle different error codes
            if response.status_code == 404:
                logging.error("[%s] Torrent %s not found (HTTP 404) during resume. "
                             "It may have been removed.", self.name, torrent_hash)
            else:
                logging.warning("[%s] Failed to resume torrent %s: HTTP %s - %s",
                               self.name, torrent_hash, response.status_code, response.text)
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("[%s] Error resuming torrent %s: %s", self.name, torrent_hash, e)
            return False

    def rename_torrent(self, torrent_hash, new_name):
        """Rename a torrent with retry logic"""
        for attempt in range(self.max_retries):
            try:
                data = {'hash': torrent_hash, 'name': new_name}
                response = self.session.post(
                    f'{self.base_url}/api/v2/torrents/rename',
                    data=data,
                    timeout=(10, self.connection_timeout)
                )
                if response.status_code == 200:
                    logging.info("[%s] Successfully renamed torrent %s", self.name, torrent_hash)
                    return True
                logging.warning("[%s] Failed to rename torrent %s (attempt %s): HTTP %s",
                               self.name, torrent_hash, attempt + 1, response.status_code)
            except requests.exceptions.ConnectTimeout:
                logging.error("[%s] Connection timeout when renaming torrent %s (attempt %s)",
                             self.name, torrent_hash, attempt + 1)
            except requests.exceptions.ConnectionError as e:
                logging.error("[%s] Connection error when renaming torrent %s (attempt %s): %s",
                             self.name, torrent_hash, attempt + 1, e)
            except requests.exceptions.Timeout as e:
                logging.error("[%s] Timeout when renaming torrent %s (attempt %s): %s",
                             self.name, torrent_hash, attempt + 1, e)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("[%s] Error renaming torrent %s (attempt %s): %s",
                             self.name, torrent_hash, attempt + 1, e)

            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        return False

    def get_torrent_state(self, torrent_hash):
        """Get the current state of a torrent"""
        try:
            response = self.session.get(
                f'{self.base_url}/api/v2/torrents/info?hashes={torrent_hash}',
                timeout=(10, self.connection_timeout)
            )
            if response.status_code == 200:
                torrents = response.json()
                if torrents:
                    state = torrents[0].get('state', 'unknown')
                    progress = torrents[0].get('progress', 0)
                    logging.debug("[%s] Torrent %s state: %s (%.1f%% complete)", 
                                 self.name, torrent_hash, state, progress * 100)
                    return state, progress
            return 'unknown', 0
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("[%s] Error getting torrent state for %s: %s", 
                         self.name, torrent_hash, e)
            return 'unknown', 0

    def _normalize_torrent_hash(self, torrent_hash):
        """Normalize torrent hash format for API calls"""
        if not torrent_hash:
            return torrent_hash
        
        # qBittorrent API typically expects lowercase hashes
        normalized = torrent_hash.lower().strip()
        
        # Basic validation - should be 40 character hex string
        if len(normalized) != 40 or not all(c in '0123456789abcdef' for c in normalized):
            logging.warning("[%s] Torrent hash format may be invalid: %s", 
                           self.name, torrent_hash)
        
        return normalized

    def _force_complete_torrent(self, torrent_hash):
        """Force complete a torrent to release file locks"""
        try:
            normalized_hash = self._normalize_torrent_hash(torrent_hash)
            data = {'hashes': normalized_hash}
            url = f'{self.base_url}/api/v2/torrents/setForceStart'
            logging.debug("[%s] Attempting to force start torrent %s (normalized: %s) using URL: %s", 
                         self.name, torrent_hash, normalized_hash, url)
            
            response = self.session.post(
                url,
                data=data,
                timeout=(10, self.connection_timeout)
            )
            
            logging.debug("[%s] Force start response: HTTP %s, Content: %s", 
                         self.name, response.status_code, response.text[:200])
            
            if response.status_code == 200:
                logging.info("[%s] Force started torrent %s", self.name, torrent_hash)
                time.sleep(2)  # Wait a bit
                # Now pause it
                pause_result = self.pause_torrent(torrent_hash)
                if not pause_result:
                    logging.warning("[%s] Force start succeeded but pause failed for %s", 
                                   self.name, torrent_hash)
                return pause_result  # Only return True if both succeeded
            elif response.status_code == 404:
                logging.error("[%s] Torrent %s not found (HTTP 404) during force start. "
                             "It may have been removed.", self.name, torrent_hash)
            else:
                logging.warning("[%s] Failed to force start torrent %s: HTTP %s - %s",
                               self.name, torrent_hash, response.status_code, response.text)
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("[%s] Error force starting torrent %s: %s", self.name, torrent_hash, e)
            return False

    def _attempt_rename_with_pause(self, torrent_hash, data, attempt=0):
        """Helper method to attempt rename after pausing torrent with aggressive strategies"""
        # First, check torrent state to understand what we're dealing with
        state, progress = self.get_torrent_state(torrent_hash)
        logging.info("[%s] Before aggressive rename - Torrent state: %s (%.1f%% complete)", 
                    self.name, state, progress * 100)
        
        strategies = [
            ("pause", lambda: self.pause_torrent(torrent_hash)),
            ("force_complete_then_pause", lambda: self._force_complete_torrent(torrent_hash)),
            ("wait_and_retry", lambda: True),  # Always succeeds, just waits longer
        ]
        
        for strategy_name, strategy_func in strategies:
            logging.info("[%s] Trying strategy '%s' for torrent %s", 
                        self.name, strategy_name, torrent_hash)
            
            if not strategy_func():
                logging.warning("[%s] Strategy '%s' failed", self.name, strategy_name)
                continue
            
            # Wait longer for folders as they might have more file handles
            # Also wait longer if torrent is actively downloading/seeding
            if strategy_name == "wait_and_retry":
                # For the wait_and_retry strategy, use much longer waits
                base_wait = 30 + (attempt * 10)  # 30, 40, 50, ... seconds
                logging.info("[%s] Using extended wait strategy: %s seconds", 
                            self.name, base_wait)
            else:
                base_wait = 10 if attempt > 0 else 5
                if state in ['downloading', 'uploading', 'stalledDL', 'stalledUP']:
                    base_wait *= 2
            
            logging.info("[%s] Waiting %s seconds after %s (torrent was %s)...", 
                        self.name, base_wait, strategy_name, state)
            time.sleep(base_wait)
            
            # Check state again after our strategy
            new_state, _ = self.get_torrent_state(torrent_hash)
            logging.debug("[%s] After %s strategy - Torrent state: %s", 
                         self.name, strategy_name, new_state)
            
            try:
                response_retry = self.session.post(
                    f'{self.base_url}/api/v2/torrents/renameFile',
                    data=data,
                    timeout=(10, self.connection_timeout)
                )
                
                if response_retry.status_code == 200:
                    logging.info("[%s] Successfully renamed after %s strategy", 
                               self.name, strategy_name)
                    return True
                elif response_retry.status_code == 409:
                    logging.warning("[%s] Still getting conflict after %s strategy, "
                                   "torrent state: %s", self.name, strategy_name, new_state)
                else:
                    logging.warning("[%s] Got HTTP %s after %s strategy: %s", 
                                  self.name, response_retry.status_code, strategy_name, 
                                  response_retry.text[:100])
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("[%s] Error during rename after %s: %s", 
                             self.name, strategy_name, e)
            finally:
                # Only try to resume if we actually paused (and it worked)
                if strategy_name in ["pause", "force_complete_then_pause"]:
                    self.resume_torrent(torrent_hash)
            
            # Small delay before trying next strategy
            if strategy_name != strategies[-1][0]:  # Not the last strategy
                time.sleep(3)
        
        logging.error("[%s] All aggressive strategies exhausted for torrent %s", 
                     self.name, torrent_hash)
        return False

    def _handle_rename_response(self, response, torrent_hash, old_path, new_path,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                               is_folder, attempt):
        """Helper method to handle rename response and conflicts"""
        if response.status_code == 200:
            logging.info("[%s] Successfully renamed %s in torrent %s",
                       self.name, 'folder' if is_folder else 'file', torrent_hash)
            return True, False  # success, should_break

        if response.status_code == 409:
            # Get torrent state to better understand the conflict
            state, progress = self.get_torrent_state(torrent_hash)
            
            logging.warning("[%s] Conflict when renaming %s '%s' (attempt %s): "
                           "File may be in use. Torrent state: %s (%.1f%% complete)", 
                           self.name, 'folder' if is_folder else 'file', old_path, 
                           attempt + 1, state, progress * 100)
            
            # For folders, be more aggressive - try pausing immediately
            # For files, wait until attempt 2 as before
            should_try_pause = is_folder or attempt >= 1
            
            if should_try_pause:
                logging.info("[%s] Attempting aggressive rename strategies for %s '%s' "
                            "(torrent state: %s)...", 
                            self.name, 'folder' if is_folder else 'file', old_path, state)
                data = {'hash': torrent_hash, 'oldPath': old_path, 'newPath': new_path}
                if self._attempt_rename_with_pause(torrent_hash, data, attempt):
                    return True, False  # success, should_break
                else:
                    logging.error("[%s] All aggressive strategies failed for %s '%s'", 
                                 self.name, 'folder' if is_folder else 'file', old_path)
            else:
                logging.info("[%s] Skipping aggressive strategies for now (attempt %s/%s), "
                            "will try on next attempt", 
                            self.name, attempt + 1, 5)  # Assuming max 5 retries
            
            return False, False  # no success, continue trying

        if response.status_code == 400:
            logging.error("[%s] Bad request when renaming %s %s (attempt %s): %s",
                         self.name, 'folder' if is_folder else 'file', old_path,
                         attempt + 1, response.text)
            return False, True  # no success, should_break

        logging.warning("[%s] Failed to rename %s %s (attempt %s): HTTP %s",
                       self.name, 'folder' if is_folder else 'file', old_path,
                       attempt + 1, response.status_code)
        return False, False  # no success, continue trying

    def rename_file(self, torrent_hash, old_path, new_path, is_folder=False):
        """Rename a file/folder in torrent with retry logic and torrent pausing for conflicts"""
        max_retries = self.max_retries
        retry_delay = self.retry_delay if not is_folder else self.folder_retry_delay

        for attempt in range(max_retries):
            try:
                data = {'hash': torrent_hash, 'oldPath': old_path, 'newPath': new_path}
                response = self.session.post(
                    f'{self.base_url}/api/v2/torrents/renameFile',
                    data=data,
                    timeout=(10, self.connection_timeout)
                )

                success, should_break = self._handle_rename_response(
                    response, torrent_hash, old_path, new_path, is_folder, attempt)

                if success:
                    return True
                if should_break:
                    break

            except requests.exceptions.ConnectTimeout:
                logging.error("[%s] Connection timeout when renaming %s %s (attempt %s)",
                             self.name, 'folder' if is_folder else 'file', old_path, attempt + 1)
            except requests.exceptions.ConnectionError as e:
                logging.error("[%s] Connection error when renaming %s %s (attempt %s): %s",
                             self.name, 'folder' if is_folder else 'file', old_path, attempt + 1, e)
            except requests.exceptions.Timeout as e:
                logging.error("[%s] Timeout when renaming %s %s (attempt %s): %s",
                             self.name, 'folder' if is_folder else 'file', old_path, attempt + 1, e)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("[%s] Error renaming %s %s (attempt %s): %s",
                             self.name, 'folder' if is_folder else 'file', old_path, attempt + 1, e)

            if attempt < max_retries - 1:
                # Use longer delays for folders after conflicts, especially aggressive ones
                effective_delay = retry_delay
                if is_folder and attempt > 0:
                    effective_delay = min(retry_delay * 2, 60)  # Double delay but max 60 seconds
                
                logging.info("[%s] Waiting %s seconds before retry (attempt %s/%s)...", 
                           self.name, effective_delay, attempt + 1, max_retries)
                time.sleep(effective_delay)

        return False

class QBittorrentMultiMonitor:
    """
    Multi-instance qBittorrent monitoring system.

    This class manages multiple qBittorrent instances, coordinating monitoring
    operations across all configured instances. It loads configuration from
    environment variables and runs concurrent monitoring threads.

    The monitor automatically detects domain names and URLs in torrent names,
    folder names, and filenames, then removes them to create cleaner, more
    readable torrent content names.

    Attributes:
        instances (List[QBittorrentInstance]): List of configured qBittorrent instances
        running (bool): Flag indicating if monitoring is active
    """
    def __init__(self):
        self.instances = self.load_instances_from_env()
        self.running = False

    def load_instances_from_env(self):
        """Load qBittorrent instances from environment variables"""
        instances = []

        # Look for environment variables with pattern QBITTORRENT_<INDEX>_<PROPERTY>
        index = 0
        while True:
            url_var = f'QBITTORRENT_{index}_URL'
            if url_var not in os.environ:
                break

            url = os.environ[url_var]
            name = os.environ.get(f'QBITTORRENT_{index}_NAME', f'qbit-{index}')
            username = os.environ.get(f'QBITTORRENT_{index}_USERNAME', 'admin')
            password = os.environ.get(f'QBITTORRENT_{index}_PASSWORD', 'adminadmin')
            check_interval = int(os.environ.get(f'QBITTORRENT_{index}_CHECK_INTERVAL', '30'))
            max_retries = int(os.environ.get(f'QBITTORRENT_{index}_MAX_RETRIES', '8'))
            retry_delay = int(os.environ.get(f'QBITTORRENT_{index}_RETRY_DELAY', '15'))
            folder_retry_delay = int(os.environ.get(
                f'QBITTORRENT_{index}_FOLDER_RETRY_DELAY', '45'
            ))
            connection_timeout = int(os.environ.get(
                f'QBITTORRENT_{index}_CONNECTION_TIMEOUT', '30'
            ))

            instance = QBittorrentInstance(
                name=name,
                url=url,
                username=username,
                password=password,
                check_interval=check_interval,
                max_retries=max_retries,
                retry_delay=retry_delay,
                folder_retry_delay=folder_retry_delay,
                connection_timeout=connection_timeout
            )

            instances.append(instance)
            logging.info("Added qBittorrent instance: %s (%s)", name, url)
            index += 1

        if not instances:
            logging.warning("No qBittorrent instances configured via environment variables")

        return instances

    def extract_domain_v2(self, text):
        """Enhanced domain extraction with better validation"""
        # Look for actual URLs or domains with common patterns
        url_pattern = (r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.'
                      r'[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?')
        matches = re.findall(url_pattern, text, re.IGNORECASE)

        for match in matches:
            full_match = re.search(r'(?:https?://)?(?:www\.)?' + re.escape(match),
                                 text, re.IGNORECASE)
            if full_match:
                full_url = full_match.group(0)
                if ('http://' in full_url.lower() or
                    'https://' in full_url.lower() or
                    'www.' in full_url.lower() or
                    any(tld in full_url.lower() for tld in ['.com', '.org', '.net', '.tv',
                                                           '.io', '.co', '.uk', '.de', '.fr',
                                                           '.ru', '.kim', '.xyz', '.top',
                                                           '.site', '.info'])):
                    if len(match) > 6 and match.count('.') <= 2:
                        return full_url

        return None

    def clean_name(self, name, domain):
        """Remove domain from name while preserving file extensions"""
        if not domain:
            return name

        try:
            # Split the name to preserve file extension (for files, not folders)
            path_parts = name.split('/')
            filename = path_parts[-1]
            directory_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''

            # Check if this looks like a file (has extension) or folder
            file_parts = filename.rsplit('.', 1)
            is_file = (len(file_parts) > 1 and len(file_parts[1]) <= 6 and len(file_parts[1]) > 0)

            if is_file:
                # Handle file: preserve extension
                base_name = file_parts[0]
                file_extension = '.' + file_parts[1]

                # Remove domain from base name only
                cleaned_base = base_name
                if domain in base_name:
                    cleaned_base = re.sub(re.escape(domain), '', cleaned_base, flags=re.IGNORECASE)
                    cleaned_base = re.sub(r'[-_.\[\](){}]+', ' ', cleaned_base)
                    cleaned_base = re.sub(r'\s+', ' ', cleaned_base).strip()

                # Handle case where cleaning results in empty string
                if not cleaned_base:
                    cleaned_base = base_name

                # Reconstruct filename with preserved extension
                final_name = cleaned_base + file_extension
            else:
                # Handle folder: clean the entire folder name
                cleaned_name = filename
                if domain in filename:
                    cleaned_name = re.sub(re.escape(domain), '', cleaned_name, flags=re.IGNORECASE)
                    cleaned_name = re.sub(r'[-_.\[\](){}]+', ' ', cleaned_name)
                    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()

                final_name = cleaned_name if cleaned_name else filename

            # Reconstruct full path
            if directory_path:
                result = directory_path + '/' + final_name
            else:
                result = final_name

            return result if result != name else name
        except (re.error, AttributeError, IndexError, TypeError) as e:
            logging.error("[Generic] Error cleaning name '%s': %s", name, e)
            return name

    def get_unique_paths(self, files):
        """Extract unique folder paths from file list"""
        paths = set()
        for file in files:
            path_parts = file['name'].split('/')
            # Add all parent directories
            for i in range(len(path_parts) - 1):  # Don't include the file itself
                if i < len(path_parts) - 1:  # Only folders, not files
                    path = '/'.join(path_parts[:i+1])
                    if path:
                        paths.add(path)
        return sorted(list(paths))

    def _process_folder_path(self, instance, torrent_hash, folder_path, files):
        """Helper method to process a single folder path"""
        processed_count = 0
        domain_in_folder = self.extract_domain_v2(folder_path)

        if not domain_in_folder:
            logging.debug("[%s]   No domain found in folder: \"%s\"",
                         instance.name, folder_path)
            return processed_count

        new_folder_path = self.clean_name(folder_path, domain_in_folder)
        if new_folder_path == folder_path:
            logging.debug("[%s]   Folder name unchanged: \"%s\"",
                         instance.name, folder_path)
            return processed_count

        logging.info("[%s]   Renaming folder: \"%s\" -> \"%s\"",
                    instance.name, folder_path, new_folder_path)

        if instance.rename_file(torrent_hash, folder_path, new_folder_path, is_folder=True):
            processed_count += 1
            # Update file paths to reflect folder renaming
            for file in files:
                if file['name'].startswith(folder_path + '/'):
                    file['name'] = new_folder_path + file['name'][len(folder_path):]
        else:
            logging.error("[%s]   Failed to rename folder: \"%s\"",
                         instance.name, folder_path)

        return processed_count

    def _process_file(self, instance, torrent_hash, file_name):
        """Helper method to process a single file"""
        domain_in_file = self.extract_domain_v2(file_name)

        if not domain_in_file:
            logging.debug("[%s]   No domain found in file: \"%s\"",
                         instance.name, file_name)
            return 0

        new_file_name = self.clean_name(file_name, domain_in_file)
        if new_file_name == file_name:
            logging.debug("[%s]   File name unchanged: \"%s\"",
                         instance.name, file_name)
            return 0

        logging.info("[%s]   Renaming file: \"%s\" -> \"%s\"",
                    instance.name, file_name, new_file_name)

        if instance.rename_file(torrent_hash, file_name, new_file_name, is_folder=False):
            return 1

        logging.error("[%s]   Failed to rename file: \"%s\"", instance.name, file_name)
        return 0

    def process_torrent_paths(self, instance, torrent_hash, files):
        """Process all paths (folders and files) in a torrent"""
        processed_count = 0

        # Get unique folder paths
        folder_paths = self.get_unique_paths(files)
        logging.debug("[%s] Found folder paths: %s", instance.name, folder_paths)

        # Process folders (from deepest to shallowest to avoid conflicts)
        sorted_folders = sorted(folder_paths, key=lambda x: x.count('/'), reverse=True)

        for folder_path in sorted_folders:
            processed_count += self._process_folder_path(instance, torrent_hash,
                                                       folder_path, files)

        # Process files (with updated paths if folders were renamed)
        for file in files:
            processed_count += self._process_file(instance, torrent_hash, file['name'])

        return processed_count

    def process_torrent(self, instance, torrent):
        """Process a single torrent"""
        torrent_name = torrent['name']
        torrent_hash = torrent['hash']

        logging.info("[%s] Processing torrent: %s (%s)",
                    instance.name, torrent_name, torrent_hash)

        # Check if torrent name contains a domain
        domain = self.extract_domain_v2(torrent_name)

        if domain:
            new_torrent_name = self.clean_name(torrent_name, domain)
            if new_torrent_name != torrent_name:
                logging.info("[%s] Renaming torrent: \"%s\" -> \"%s\"",
                            instance.name, torrent_name, new_torrent_name)
                instance.rename_torrent(torrent_hash, new_torrent_name)
            else:
                logging.debug("[%s] Torrent name unchanged: \"%s\"",
                             instance.name, torrent_name)
        else:
            logging.debug("[%s] No domain found in torrent name: \"%s\"",
                         instance.name, torrent_name)

        # Process files and folders in torrent
        logging.info("[%s] Fetching files for torrent %s",
                    instance.name, torrent_hash)
        files = instance.get_torrent_files(torrent_hash)

        if files:
            logging.info("[%s] Found %s files in torrent", instance.name, len(files))
            files_processed = self.process_torrent_paths(instance, torrent_hash, files)
            logging.info("[%s] Processed %s paths in torrent %s",
                        instance.name, files_processed, torrent_hash)
        else:
            logging.warning("[%s] No files found for torrent %s", instance.name, torrent_hash)

    def monitor_instance(self, instance):
        """Monitor a single qBittorrent instance"""
        logging.info("[%s] Starting monitor for %s", instance.name, instance.base_url)

        # Login initially
        if not instance.login():
            logging.error("[%s] Failed initial login, will retry later", instance.name)

        while self.running:
            try:
                if not instance.should_retry():
                    time.sleep(30)
                    continue

                # Try to get torrents
                torrents = instance.get_torrents()
                if not torrents:
                    if instance.should_retry():
                        logging.warning("[%s] No torrents returned, retrying...", instance.name)
                        time.sleep(instance.check_interval)
                    continue

                # Process torrents
                for torrent in torrents:
                    try:
                        self.process_torrent(instance, torrent)
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logging.error("[%s] Error processing torrent %s: %s",
                                     instance.name, torrent.get('hash', 'unknown'), e)

                time.sleep(instance.check_interval)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("[%s] Error in monitoring loop: %s", instance.name, e)
                instance.handle_error()
                time.sleep(60)

    def start(self):
        """Start monitoring all instances"""
        if not self.instances:
            logging.error("No instances to monitor")
            return

        self.running = True
        logging.info("Starting multi-instance monitor for %s qBittorrent servers",
                    len(self.instances))

        # Use ThreadPoolExecutor to run each instance monitor in parallel
        with ThreadPoolExecutor(max_workers=len(self.instances)) as executor:
            futures = [executor.submit(self.monitor_instance, instance)
                      for instance in self.instances]

            try:
                # Wait for all threads
                for future in futures:
                    future.result()
            except KeyboardInterrupt:
                logging.info("Monitor stopped by user")
                self.running = False

def main():
    """Main entry point for the qBittorrent multi-instance monitor application."""
    monitor = QBittorrentMultiMonitor()
    monitor.start()

if __name__ == '__main__':
    main()
