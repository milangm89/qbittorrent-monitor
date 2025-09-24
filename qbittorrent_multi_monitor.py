import requests
import re
import time
import json
import os
from datetime import datetime
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/qbittorrent_monitor.log'),
        logging.StreamHandler()
    ]
)

class QBittorrentInstance:
    def __init__(self, name, url, username, password, check_interval=30, max_retries=5, retry_delay=10, folder_retry_delay=30, connection_timeout=30):
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
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
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
                logging.info(f"[{self.name}] Successfully logged in to qBittorrent")
                self.last_error_time = None
                self.error_count = 0
                return True
            else:
                logging.error(f"[{self.name}] Failed to login to qBittorrent: {response.text}")
                return False
        except requests.exceptions.ConnectTimeout:
            logging.error(f"[{self.name}] Connection timeout when connecting to {self.base_url}")
            self.handle_error()
            return False
        except requests.exceptions.ConnectionError as e:
            logging.error(f"[{self.name}] Connection error when connecting to {self.base_url}: {e}")
            self.handle_error()
            return False
        except requests.exceptions.Timeout as e:
            logging.error(f"[{self.name}] Timeout when connecting to {self.base_url}: {e}")
            self.handle_error()
            return False
        except Exception as e:
            logging.error(f"[{self.name}] Unexpected error logging in: {e}")
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
        wait_time = min(300, 30 * (2 ** (self.error_count - 1)))  # Max 5 minutes
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
            else:
                logging.error(f"[{self.name}] Failed to get torrents: HTTP {response.status_code}")
                return []
        except requests.exceptions.ConnectTimeout:
            logging.error(f"[{self.name}] Connection timeout when fetching torrents from {self.base_url}")
            self.handle_error()
            return []
        except requests.exceptions.ConnectionError as e:
            logging.error(f"[{self.name}] Connection error when fetching torrents from {self.base_url}: {e}")
            self.handle_error()
            return []
        except requests.exceptions.Timeout as e:
            logging.error(f"[{self.name}] Timeout when fetching torrents from {self.base_url}: {e}")
            self.handle_error()
            return []
        except Exception as e:
            logging.error(f"[{self.name}] Error fetching torrents: {e}")
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
            else:
                logging.error(f"[{self.name}] Failed to get files for torrent {torrent_hash}: HTTP {response.status_code}")
                return []
        except requests.exceptions.ConnectTimeout:
            logging.error(f"[{self.name}] Connection timeout when fetching files for torrent {torrent_hash}")
            return []
        except requests.exceptions.ConnectionError as e:
            logging.error(f"[{self.name}] Connection error when fetching files for torrent {torrent_hash}: {e}")
            return []
        except requests.exceptions.Timeout as e:
            logging.error(f"[{self.name}] Timeout when fetching files for torrent {torrent_hash}: {e}")
            return []
        except Exception as e:
            logging.error(f"[{self.name}] Error fetching torrent files for {torrent_hash}: {e}")
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
            else:
                logging.debug(f"[{self.name}] Could not get properties for torrent {torrent_hash}: HTTP {response.status_code}")
                return None
        except Exception as e:
            logging.debug(f"[{self.name}] Error getting torrent properties for {torrent_hash}: {e}")
            return None

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
                    logging.info(f"[{self.name}] Successfully renamed torrent {torrent_hash}")
                    return True
                else:
                    logging.warning(f"[{self.name}] Failed to rename torrent {torrent_hash} (attempt {attempt + 1}): HTTP {response.status_code}")
            except requests.exceptions.ConnectTimeout:
                logging.error(f"[{self.name}] Connection timeout when renaming torrent {torrent_hash} (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError as e:
                logging.error(f"[{self.name}] Connection error when renaming torrent {torrent_hash} (attempt {attempt + 1}): {e}")
            except requests.exceptions.Timeout as e:
                logging.error(f"[{self.name}] Timeout when renaming torrent {torrent_hash} (attempt {attempt + 1}): {e}")
            except Exception as e:
                logging.error(f"[{self.name}] Error renaming torrent {torrent_hash} (attempt {attempt + 1}): {e}")
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        return False

    def rename_file(self, torrent_hash, old_path, new_path, is_folder=False):
        """Rename a file/folder in torrent with retry logic"""
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
                
                if response.status_code == 200:
                    logging.info(f"[{self.name}] Successfully renamed {'folder' if is_folder else 'file'} in torrent {torrent_hash}")
                    return True
                elif response.status_code == 409:
                    logging.warning(f"[{self.name}] Conflict when renaming {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1}): File may be in use")
                elif response.status_code == 400:
                    logging.error(f"[{self.name}] Bad request when renaming {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1}): {response.text}")
                    break  # Don't retry on bad requests
                else:
                    logging.warning(f"[{self.name}] Failed to rename {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1}): HTTP {response.status_code}")
                    
            except requests.exceptions.ConnectTimeout:
                logging.error(f"[{self.name}] Connection timeout when renaming {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError as e:
                logging.error(f"[{self.name}] Connection error when renaming {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1}): {e}")
            except requests.exceptions.Timeout as e:
                logging.error(f"[{self.name}] Timeout when renaming {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1}): {e}")
            except Exception as e:
                logging.error(f"[{self.name}] Error renaming {'folder' if is_folder else 'file'} {old_path} (attempt {attempt + 1}): {e}")
            
            if attempt < max_retries - 1:
                logging.info(f"[{self.name}] Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
        
        return False

class QBittorrentMultiMonitor:
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
            check_interval = os.environ.get(f'QBITTORRENT_{index}_CHECK_INTERVAL', '30')
            max_retries = os.environ.get(f'QBITTORRENT_{index}_MAX_RETRIES', '5')
            retry_delay = os.environ.get(f'QBITTORRENT_{index}_RETRY_DELAY', '10')
            folder_retry_delay = os.environ.get(f'QBITTORRENT_{index}_FOLDER_RETRY_DELAY', '30')
            connection_timeout = os.environ.get(f'QBITTORRENT_{index}_CONNECTION_TIMEOUT', '30')
            
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
            logging.info(f"Added qBittorrent instance: {name} ({url})")
            index += 1
        
        if not instances:
            logging.warning("No qBittorrent instances configured via environment variables")
            
        return instances

    def extract_domain_v2(self, text):
        """Enhanced domain extraction with better validation"""
        # Look for actual URLs or domains with common patterns
        # This regex matches: http://domain.com, https://domain.com, www.domain.com
        # But with stricter validation to avoid false positives
        url_pattern = r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?'
        matches = re.findall(url_pattern, text, re.IGNORECASE)
        
        # Validate matches more carefully - only match if it's part of a proper URL pattern
        for match in matches:
            # Look for the full match in context
            full_match = re.search(r'(?:https?://)?(?:www\.)?' + re.escape(match), text, re.IGNORECASE)
            if full_match:
                full_url = full_match.group(0)
                # Check if it's a proper domain pattern by looking for common indicators
                if ('http://' in full_url.lower() or 
                    'https://' in full_url.lower() or 
                    'www.' in full_url.lower() or
                    any(tld in full_url.lower() for tld in ['.com', '.org', '.net', '.tv', '.io', '.co', '.uk', '.de', '.fr', '.ru', '.kim', '.xyz', '.top', '.site', '.info'])):
                    # Additional validation: make sure it's not just a word.word pattern
                    if len(match) > 6 and match.count('.') <= 2:  # At least 6 chars, max 2 dots
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
                
                # Remove domain from base name only - using more specific replacement
                cleaned_base = base_name
                if domain in base_name:
                    # Remove the full domain match
                    cleaned_base = re.sub(re.escape(domain), '', cleaned_base, flags=re.IGNORECASE)
                    # Clean up surrounding characters but preserve meaningful separators
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
                    # Clean up surrounding characters but preserve meaningful separators
                    cleaned_name = re.sub(r'[-_.\[\](){}]+', ' ', cleaned_name)
                    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
                
                final_name = cleaned_name if cleaned_name else filename
            
            # Reconstruct full path
            if directory_path:
                result = directory_path + '/' + final_name
            else:
                result = final_name
                
            return result if result != name else name
        except Exception as e:
            logging.error(f"[Generic] Error cleaning name '{name}': {e}")
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

    def process_torrent_paths(self, instance, torrent_hash, files):
        """Process all paths (folders and files) in a torrent"""
        processed_count = 0
        
        # Get unique folder paths
        folder_paths = self.get_unique_paths(files)
        logging.debug(f"[{instance.name}] Found folder paths: {folder_paths}")
        
        # Process folders (from deepest to shallowest to avoid conflicts)
        sorted_folders = sorted(folder_paths, key=lambda x: x.count('/'), reverse=True)
        
        for folder_path in sorted_folders:
            domain_in_folder = self.extract_domain_v2(folder_path)
            if domain_in_folder:
                new_folder_path = self.clean_name(folder_path, domain_in_folder)
                if new_folder_path != folder_path:
                    logging.info(f'[{instance.name}]   Renaming folder: "{folder_path}" -> "{new_folder_path}"')
                    if instance.rename_file(torrent_hash, folder_path, new_folder_path, is_folder=True):
                        processed_count += 1
                        # Update file paths to reflect folder renaming
                        for file in files:
                            if file['name'].startswith(folder_path + '/'):
                                file['name'] = new_folder_path + file['name'][len(folder_path):]
                    else:
                        logging.error(f'[{instance.name}]   Failed to rename folder: "{folder_path}"')
                else:
                    logging.debug(f'[{instance.name}]   Folder name unchanged: "{folder_path}"')
            else:
                logging.debug(f'[{instance.name}]   No domain found in folder: "{folder_path}"')
        
        # Process files (with updated paths if folders were renamed)
        for file in files:
            file_name = file['name']
            domain_in_file = self.extract_domain_v2(file_name)
            if domain_in_file:
                new_file_name = self.clean_name(file_name, domain_in_file)
                if new_file_name != file_name:
                    logging.info(f'[{instance.name}]   Renaming file: "{file_name}" -> "{new_file_name}"')
                    if instance.rename_file(torrent_hash, file_name, new_file_name, is_folder=False):
                        processed_count += 1
                    else:
                        logging.error(f'[{instance.name}]   Failed to rename file: "{file_name}"')
                else:
                    logging.debug(f'[{instance.name}]   File name unchanged: "{file_name}"')
            else:
                logging.debug(f'[{instance.name}]   No domain found in file: "{file_name}"')
                
        return processed_count

    def process_torrent(self, instance, torrent):
        """Process a single torrent"""
        torrent_name = torrent['name']
        torrent_hash = torrent['hash']
        
        logging.info(f"[{instance.name}] Processing torrent: {torrent_name} ({torrent_hash})")
        
        # Check if torrent name contains a domain
        domain = self.extract_domain_v2(torrent_name)
        torrent_renamed = False
        
        if domain:
            new_torrent_name = self.clean_name(torrent_name, domain)
            if new_torrent_name != torrent_name:
                logging.info(f'[{instance.name}] Renaming torrent: "{torrent_name}" -> "{new_torrent_name}"')
                torrent_renamed = instance.rename_torrent(torrent_hash, new_torrent_name)
            else:
                logging.debug(f'[{instance.name}] Torrent name unchanged: "{torrent_name}"')
        else:
            logging.debug(f'[{instance.name}] No domain found in torrent name: "{torrent_name}"')
        
        # Process files and folders in torrent
        logging.info(f"[{instance.name}] Fetching files for torrent {torrent_hash}")
        files = instance.get_torrent_files(torrent_hash)
        
        if files:
            logging.info(f"[{instance.name}] Found {len(files)} files in torrent")
            files_processed = self.process_torrent_paths(instance, torrent_hash, files)
            logging.info(f"[{instance.name}] Processed {files_processed} paths in torrent {torrent_hash}")
        else:
            logging.warning(f"[{instance.name}] No files found for torrent {torrent_hash}")

    def monitor_instance(self, instance):
        """Monitor a single qBittorrent instance"""
        logging.info(f"[{instance.name}] Starting monitor for {instance.base_url}")
        
        # Login initially
        if not instance.login():
            logging.error(f"[{instance.name}] Failed initial login, will retry later")
        
        while self.running:
            try:
                if not instance.should_retry():
                    time.sleep(30)
                    continue
                    
                # Try to get torrents
                torrents = instance.get_torrents()
                if not torrents:
                    if instance.should_retry():
                        logging.warning(f"[{instance.name}] No torrents returned, retrying...")
                        time.sleep(instance.check_interval)
                    continue
                
                # Process torrents
                for torrent in torrents:
                    try:
                        self.process_torrent(instance, torrent)
                    except Exception as e:
                        logging.error(f"[{instance.name}] Error processing torrent {torrent.get('hash', 'unknown')}: {e}")
                
                time.sleep(instance.check_interval)
                
            except Exception as e:
                logging.error(f"[{instance.name}] Error in monitoring loop: {e}")
                instance.handle_error()
                time.sleep(60)

    def start(self):
        """Start monitoring all instances"""
        if not self.instances:
            logging.error("No instances to monitor")
            return
            
        self.running = True
        logging.info(f"Starting multi-instance monitor for {len(self.instances)} qBittorrent servers")
        
        # Use ThreadPoolExecutor to run each instance monitor in parallel
        with ThreadPoolExecutor(max_workers=len(self.instances)) as executor:
            futures = [executor.submit(self.monitor_instance, instance) for instance in self.instances]
            
            try:
                # Wait for all threads
                for future in futures:
                    future.result()
            except KeyboardInterrupt:
                logging.info("Monitor stopped by user")
                self.running = False

def main():
    monitor = QBittorrentMultiMonitor()
    monitor.start()

if __name__ == '__main__':
    main()