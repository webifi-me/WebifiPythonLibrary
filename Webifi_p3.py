#!/usr/bin/python

"""
Webifi Ltd assumes no responsibility or liability for the use of the software.
This software is supplied "AS IS" without any warranties. Webifi Ltd reserves 
the right to make changes in the software without notification. This software can be 
freely distributed but must only be used with the service provided by Webifi Ltd.

The latest version of this library uses HTML5 WebSocket. To install please run:
pip install websocket-client
"""

import ssl
import threading
import queue
import calendar
import time
import http.client
from http.client import HTTPConnection, HTTPS_PORT
import ipaddress
import socket
import websocket
import logging
from logging.handlers import RotatingFileHandler


class CreateSendData:
    def __init__(self):
        """
        Object that will store the data used for building a data packet for sending to the cloud
        """
        self.data = None
        self.data_type = ""
        self.to_session_ids = []
        self.to_networks = []
        self.packet_type = None


class WebifiConstants:
    def __init__(self):
        """
        Initialise all the constants used by the Webifi Python Library
        """
        self.data_packet = -1
        self.request_credentials = -2
        self.cancel_request = -3
        self.max_packet_size = 100000
        self.minimum_download_threshold_time = 5
        self.download_error_wait_time = 5
        self.download_slippage_time = 2
        self.minimum_download_timeout = 10
        self.maximum_download_timeout = 1800
        self.default_download_request_timeout = 120
        self.download_decrease_time = 10
        self.state_request_credentials = 0
        self.state_running = 1
        self.wait_before_retry_timeout = 5

        self.ws_state_not_connected = 0
        self.ws_state_connected_not_auth = 1
        self.ws_state_connected_auth_sent = 2
        self.ws_state_set_listen_to_networks = 3
        self.ws_state_set_listen_to_networks_sent = 4
        self.ws_state_running = 5
        self.ws_state_closing_connection = 6
        self.ws_state_restart_connection = 7
        self.ws_state_waiting_for_connection = 8
        self.ws_state_connection_timeout = 9
        self.terminating_string = "~t=1"
        self.websocket_keep_alive_timeout = 30
        self.websocket_keep_alive_sent_timeout = 10
        self.websocket_thread_dead_timeout = 10

        self.use_test_server = False
        self.test_server_name = 'localhost:60061'
        self.thread_sleep_time = 0.1  # seconds


class WebifiCounters:
    def __init__(self):
        self.upload = 0
        self.download = 0


class MasterThreadVariables:
    def __init__(self):
        self.waiting_for_response = False
        self.wait_before_retry = 0
        self.stop_request_timeout_tick = None
        self.url = None
        self.retry_count = 0
        self.max_retries = 3
        self.last_packet_sent = True
        self.last_packet_uploaded = None
        self.retry_packet = None
        self.send_packet = None


class CloudSendPacket:
    def __init__(self):
        self.url = ''
        self.url_ssl = ''
        self.page = ''
        self.post_data = ''
        self.data_packet = False
        self.default_params = ''
        self.data_type = ''


class UploadResponse:
    def __init__(self):
        self.response = ''
        self.packet_type = False


class DownloadResponse:
    def __init__(self):
        self.error_code = '0'
        self.data = ''
        self.data_type = ''
        self.from_who = -1


class CreateWebifiDictionary:
    def __init__(self):
        self.keys = []
        self.values = []


# local variables used in Webifi class
class WebifiLocals:
    def __init__(self):
        self.server_ip_addr = ''
        self.server_ip_addr2 = ''
        self.download_url = ''
        self.upload_url = ''
        self.upload_params = ''
        self.download_ssl_url = ''
        self.upload_ssl_url = ''
        self.ssl_context_download = None
        self.ssl_context_upload = None
        self.auth_params = ''
        self.download_page = ''
        self.error_codes = CreateWebifiDictionary()
        self.connect_name = ''
        self.connect_password = ''
        self.network_names = []
        self.device_id = ''
        self.session_id = -1
        self.use_encryption = False
        self.service_running = False
        self.to_master_for_cloud_queue = WebifiQueue()  # special queue that allows us to push one item to the front
        self.from_to_cloud_to_master_queue = queue.Queue()
        self.from_from_cloud_to_master_queue = queue.Queue()
        self.to_cloud_queue = queue.Queue()
        self.last_sent_data = None
        self.closing_threads = False
        self.from_cloud_running = False
        self.wait_before_next_request = False
        self.last_download_successful = False
        self.restart_download = False
        self.networks_updated = False
        self.discoverable = True
        self.headers = {'Content-type': 'application/octet-stream'}
        self.log_level = logging.ERROR

        # counters
        self.counters = WebifiCounters()

        # state
        self.constants = WebifiConstants()
        self.webifi_state = self.constants.state_request_credentials
        self.download_timeout = self.constants.default_download_request_timeout

        # callbacks
        self.data_received_callback = None
        self.connection_status_callback = None
        self.error_callback = None

        # master thread variables
        self.master_vars = MasterThreadVariables()

        # threads
        self.master_thread = None
        self.master_thread_running = False
        self.master_thread_terminated = True
        self.upload_thread = None
        self.upload_thread_running = False
        self.upload_thread_terminated = True
        self.download_thread = None
        self.download_thread_running = False
        self.download_thread_terminated = True
        self.download_thread_request = False  # set to true when service is running
        self.websocket_thread = None
        self.websocket_thread_running = False
        self.websocket_thread_terminated = True

        # WebSocket
        self.websocket_state = self.constants.ws_state_not_connected
        self.tick_websocket_keep_alive = calendar.timegm(time.gmtime())
        self.keep_alive_sent = False
        self.websocket_rec_data_buf = ''
        self.websocket_receive_queue = queue.Queue()
        self.websocket_url = ''
        self.websocket_ssl_url = ''
        self.use_websocket = True
        self.set_use_websocket = False

        self.logger = logging.getLogger('webifi')


# create a new instance of a blank class
class WebifiNewInstance:
    def __init__(self):
        pass


# Custom Webifi queue which allows us to push one item back to the front.
# This is important because the last popped packet might not be able to be added to the current packet sent to the
# server, then it is important to put it back to the front of the queue
class WebifiQueue:
    def __init__(self):
        self.__queue = queue.Queue()
        self.__unshifted_item = None  # this variable hold an item that was pushed in front
        self.__queue_count = 0

    def put(self, item):
        self.__queue.put(item)
        self.__queue_count += 1

    def get(self):
        if self.__unshifted_item is not None:
            # return the value that was pushed to the front previously
            return_value = self.__unshifted_item
            self.__unshifted_item = None
            self.__queue_count -= 1
            return return_value
        else:
            self.__queue_count -= 1
            return self.__queue.get()

    def empty(self):
        if self.__queue.empty() and self.__unshifted_item is None:
            return True
        return False

    def unshift(self, item):
        self.__unshifted_item = item
        self.__queue_count += 1

    def get_size(self):
        return self.__queue_count


# main class used for communication
class Webifi:
    def __init__(self):
        self.__locals = WebifiLocals()
        self.name = 'Webifi Python Device'
        self.connected = False

    def enable_logging(self, log_filename, log_level, enable_console_logging):
        """This function will enable logging to file for debugging purposes
        :param log_filename: The file that will be used to log data, send empty string not to use file logging
        :param log_level: The minimum log level that will be logged to file
        :param enable_console_logging: If true then send log messages to console
        """
        # Add a file handler
        l = self.__locals
        l.log_level = log_level
        for h in list(l.logger.handlers):
            l.logger.removeHandler(h)
        if log_filename != "":
            filehandler = RotatingFileHandler(log_filename, maxBytes=10000, backupCount=5)
            # create a logging format
            filehandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            l.logger.addHandler(filehandler)
        # Add a console handler
        if enable_console_logging:
            consolehandler = logging.StreamHandler()
            consolehandler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
            l.logger.addHandler(consolehandler)
            l.logger.setLevel(log_level)

    def log_application_message(self, log_level, message):
        """This function allows the application to log messages to the same log file used by Webifi
        :param log_level: The log level of the user message
        :param message: The message that the user wants to log
        """
        mes = 'Application message: ' + message
        l = self.__locals
        if log_level == logging.DEBUG:
            l.logger.debug(mes)
        elif log_level == logging.INFO:
            l.logger.info(mes)
        elif log_level == logging.WARNING:
            l.logger.warning(mes)
        elif log_level == logging.ERROR:
            l.logger.error(mes)
        elif log_level == logging.CRITICAL:
            l.logger.critical(mes)

    def set_connect_name(self, connect_name):
        """Change the connect name. This can only be changed when the service is not started
        :param connect_name: Conect name that was configured on www.webifi.me
        :return: 0 if successful, 10 if failed
        """
        if self.__locals.webifi_state == self.__locals.constants.state_request_credentials:
            self.__locals.connect_name = connect_name
            return '0'
        else:
            self.__locals.logger.error('Connect name cannot be set after service has started')
            return '10'

    def set_connect_password(self, connect_password):
        """Change the connect password for the user. This can only be changed when the service is not started
        :param connect_password: The connect password on your account page when logged in at www.webifi.me.
        This is not your account password.
        :return: 0 if successful, 10 if failed
        """
        if self.__locals.webifi_state == self.__locals.constants.state_request_credentials:
            self.__locals.connect_password = connect_password
            return '0'
        else:
            self.__locals.logger.error('Password cannot be set after service has started')
            return '10'

    def set_network_names(self, network_names):
        """Change the network names that this instance must be part of. The network names can be changed after the
        service has started. For more information about network names
        please see https://www.webifi.me/how-it-works/
        :param network_names: An array of network names
        :return: 0 if successful
        """
        l = self.__locals
        l.network_names = []
        for i in range(len(network_names)):
            # remove empty strings from array
            if len(network_names[i]) > 0:
                l.network_names.append(network_names[i])
        l.networks_updated = False
        l.logger.debug('New network names set')
        if l.webifi_state == l.constants.state_running:
            if l.use_websocket:
                if l.websocket_state == l.constants.ws_state_running:
                    l.websocket_state = l.constants.ws_state_set_listen_to_networks
            else:
                # if service is already running then stop the download request so that new networks can be loaded
                self.send_cancel_request()
        return '0'

    def get_network_names(self):
        """Return the network names that this instance is part of
        :return: The network names
        """
        return self.__locals.network_names

    def set_use_websocket(self, use_websocket):
        """Enable or disable the use of WebSocket for the connection. If this setting is changed while
        the service is running then the connection will be re-established.
        :param use_websocket: True or False
        """
        l = self.__locals
        if l.use_websocket != use_websocket:
            if l.webifi_state == l.constants.state_running:
                if l.use_websocket:
                    # send websocket termination message
                    try:
                        l.websocket.send('~c=t' + l.constants.terminating_string)
                        l.websocket_state = l.constants.ws_state_closing_connection
                        l.logger.debug('WebSocket: Close connection message sent')
                    except:
                        l.logger.error('WebSocket: failed to send Close connection message')
                else:
                    # send long polling termination message
                    self.send_cancel_request()
                    l.logger.debug('WebSocket: Long polling cancel request sent')
                    l.websocket_state = l.constants.ws_state_not_connected
                    l.set_use_websocket = True
                    while not l.to_master_for_cloud_queue.empty():
                        time.sleep(0.1)    # wait for message to be sent before setting use_websocket to true
            l.use_websocket = use_websocket

    def get_use_websocket(self):
        """Return the true if websocket is enabled
        :return: Return the true if websocket is enabled
        """
        return self.__locals.use_websocket

    def set_discoverable(self, discoverable):
        """If set to True then the library will automatically respond to a discovery request
        :param discoverable: True or False
        :return: 0 if successful
        """
        self.__locals.discoverable = discoverable
        self.__locals.logger.debug('Discoverable state set to %s', discoverable)
        return '0'

    def set_download_timeout(self, value):
        """Set the amount of time in seconds the download thread will wait before starting a new request if no data
        was available. Normally user does not need to change this value
        :param value: Amount of time in seconds the download thread will wait before starting a new request if no data
        was available (min: 10 seconds, max: 600 seconds)
        """
        if value > self.__locals.constants.maximum_download_timeout:
            self.__locals.download_timeout = self.__locals.constants.maximum_download_timeout
        elif value < self.__locals.constants.minimum_download_timeout:
            self.__locals.download_timeout = self.__locals.constants.minimum_download_timeout
        else:
            self.__locals.download_timeout = value
        if self.__locals.webifi_state == self.__locals.constants.state_running:
            self.send_cancel_request(False)
        self.__locals.logger.debug('Download timeout set to %s', self.__locals.download_timeout)

    def get_download_timeout(self):
        """Return the amount of time in seconds the download thread will wait before starting a new request if no data
        was available. Normally user does not need to change this value
        :return: Amount of time in seconds the download thread will wait before starting a new request if no data was
        available
        """
        return self.__locals.download_timeout

    def get_discoverable(self):
        """Return true if the discoverable state is set
        :return: Discoverable state
        """
        return self.__locals.discoverable

    def get_connect_name(self):
        """Return connect name
        :return: The connect name
        """
        return self.__locals.connect_name

    def get_connect_password(self):
        """Return the connect password
        :return: The connect password for this instance
        """
        return self.__locals.connect_password

    def set_use_encryption(self, value):
        """Set if encryption must be used
        :param value: True or False
        """
        l = self.__locals
        if l.use_encryption != value:
            l.use_encryption = value
            if l.webifi_state == l.constants.state_running:
                if l.use_websocket:
                    l.websocket_state = l.constants.ws_state_restart_connection
                    try:
                        l.websocket.send('~c=c' + l.constants.terminating_string)
                    except:
                        l.logger.error('WebSocket: failed to send Set Encryption message')
                else:
                    self.send_cancel_request()
            l.logger.debug('Use encryption set to %s', value)

    def get_use_encryption(self):
        """Return the value if encryption is used or not
        :return: True or False
        """
        return self.__locals.use_encryption

    def get_session_id(self):
        """Get the session ID that the server assigned to this instance.
        :return: Session ID
        """
        return self.__locals.session_id

    def get_counters(self):
        """Return the upload and download counters. These counters get incremented each time an upload or download
        is done
        :return: counters variable containing counters.upload and counters.download
        """
        return self.__locals.counters

    def set_data_received_callback(self, cb):
        """Set the callback function which is called when data is received
        :param cb: callback function name
        """
        self.__locals.data_received_callback = cb

    def set_connection_status_callback(self, cb):
        """Set the callback function which is called when the connection status changed.
        :param cb: callback function name
        """
        self.__locals.connection_status_callback = cb

    def set_error_callback(self, cb):
        """Set the callback function which is called when there was an error.
        :param cb: callback function name
        """
        self.__locals.error_callback = cb

    def start(self):
        """Start the service. This function must be called for communication with the server to start. The connection
        status callback will have the result if the connection was successful
        :return: 0 if successful, 6 if the connect name or password was not set
        """
        l = self.__locals
        if l.connect_name == '':
            l.logger.error('No connect name specified')
            return '8'
        if l.connect_password == '':
            l.logger.error('No connect password specified')
            return '8'
        l.closing_threads = False
        # start master thread
        l.master_thread = threading.Thread(target=self.master_thread, args=[l.master_vars])
        l.master_thread.start()
        # start upload thread
        l.upload_thread = threading.Thread(target=self.upload_thread)
        l.upload_thread.start()
        # start download thread
        l.download_thread = threading.Thread(target=self.download_thread)
        l.download_thread.start()
        # start websocket thread
        l.websocket_thread = threading.Thread(target=self.websocket_thread)
        l.websocket_thread.start()
        return '0'

    def send_data(self, send_data):
        """Function used for sending data to the cloud
        :param send_data: data structure with all the data to be sent. The data structure can be created
        by calling CreateSendData()
        :return: return 0 if successful, 6 if sendData.data is empty
        """
        upload_data = CreateSendData()
        upload_data.data = self.tilde_encode_data(send_data.data)
        upload_data.to_session_ids = send_data.to_session_ids
        for network in send_data.to_networks:
            upload_data.to_networks.append(self.tilde_encode_data(network))
        upload_data.data_type = self.tilde_encode_data(send_data.data_type)
        upload_data.packet_type = self.__locals.constants.data_packet
        self.__locals.to_master_for_cloud_queue.put(upload_data)
        return '0'

    @staticmethod
    def test_ip_address(ip):
        """Check if an IP address is valid
        :param ip: IP address
        :return: True or False
        """
        try:
            ipaddress.ip_address(ip)
            valid = True
        except ValueError:
            valid = False
        return valid

    @staticmethod
    def get_epoch_time():
        """Get the epoch time
        :return: Return epoch time
        """
        return calendar.timegm(time.gmtime())

    @staticmethod
    def check_if_data_can_be_added(packet1, packet2):
        """Compare two upload data packets. If they are the same then their data can be concatenated
        :param packet1: First packet used in comparison
        :param packet2: Second packet used in comparison
        :return: True if packets are the same, otherwise False
        """
        the_same = True
        if packet1.data_type != packet2.data_type:
            the_same = False
        if packet1.packet_type != packet2.packet_type:
            the_same = False
        if len(packet1.to_networks) != len(packet2.to_networks):
            the_same = False
        if len(packet1.to_session_ids) != len(packet2.to_session_ids):
            the_same = False
        if the_same:
            # check if the individual to networks and session ids are the same
            for i in range(0, len(packet1.to_networks)):
                if packet1.to_networks[i] != packet2.to_networks[i]:
                    the_same = False
            for i in range(0, len(packet1.to_session_ids)):
                if packet1.to_session_ids[i] != packet2.to_session_ids[i]:
                    the_same = False
        return the_same

    @staticmethod
    def bracket_encode(data):
        """Build a string where all visible ASCII characters will be shown normally and non visible ASCII
        characters will be shown between square brackets. An opening square bracket will be [[
        :param data: The data that must be bracket encoded
        :return:
        """
        text = ""
        for i in range(0, len(data)):
            val = ord(data[i])
            if val < 32 or val > 126:
                text += '[' + str(val) + ']'
            elif data[i] == '[':
                text += '[['
            else:
                text += data[i]
        return text

    def master_thread(self, m):
        """This function must never be called directly by user. Call Start() to start the service
        :param m: variables used by master thread
        :return:
        """
        l = self.__locals
        l.master_thread_running = True
        l.master_thread_terminated = False
        l.logger.info('Master thread started')
        while l.master_thread_running:
            something_happened = False
            if m.waiting_for_response:
                if m.wait_before_retry < self.get_epoch_time():
                    something_happened = True
                    m.waiting_for_response = False
                    l.logger.error('Waiting for response timed out')
            else:
                if l.webifi_state == l.constants.state_request_credentials and not l.closing_threads:
                    # check if enough time elapsed between retries to not swamp the server
                    if m.wait_before_retry < self.get_epoch_time():
                        something_happened = True
                        if self.connected:
                            # connection failed - call connection callback
                            self.connected = False
                            if l.connection_status_callback is not None:
                                l.connection_status_callback(False)
                        m.wait_before_retry = self.get_epoch_time() + l.constants.wait_before_retry_timeout
                        m.waiting_for_response = True
                        send_packet = WebifiNewInstance()
                        if l.constants.use_test_server:
                            send_packet.url = l.constants.test_server_name
                            send_packet.url_ssl = l.constants.test_server_name
                        else:
                            send_packet.url = 'connect.webifi.me'
                            send_packet.url_ssl = 'connect.webifi.me'
                        send_packet.page = '/'
                        webifi_dict = CreateWebifiDictionary()
                        webifi_dict.keys.append('p')   # protocol number
                        webifi_dict.values.append('1')
                        webifi_dict.keys.append('cn')   # connect name
                        webifi_dict.values.append(l.connect_name)
                        webifi_dict.keys.append('cp')  # connect password
                        webifi_dict.values.append(l.connect_password)
                        webifi_dict.keys.append('ec')  # request error code descriptions
                        webifi_dict.values.append('1')
                        send_packet.post_data = Webifi.encode_webifi_protocol(webifi_dict)
                        send_packet.packet_type = l.constants.request_credentials
                        if l.to_cloud_queue.empty():
                            l.to_cloud_queue.put(send_packet)
                            l.logger.debug('Request credentials')
                        else:
                            l.logger.debug('Request credentials still waiting for previous request to complete')
                        l.networks_updated = False
                elif l.webifi_state == l.constants.state_running:
                    if l.use_websocket:
                        if l.websocket_state == l.constants.ws_state_connected_not_auth:
                            try:
                                l.websocket.send(l.auth_params + l.constants.terminating_string)
                                l.websocket_state = l.constants.ws_state_connected_auth_sent
                                m.wait_before_retry = self.get_epoch_time() + l.constants.wait_before_retry_timeout
                                m.waiting_for_response = True
                                something_happened = True
                                l.logger.debug('WebSocket: Send connection auth message')
                            except:
                                l.logger.error('WebSocket: failed to Send connection auth message')
                        elif l.websocket_state == l.constants.ws_state_set_listen_to_networks:
                            m.wait_before_retry = self.get_epoch_time() + l.constants.wait_before_retry_timeout
                            m.waiting_for_response = True
                            something_happened = True
                            l.websocket_state = l.constants.ws_state_set_listen_to_networks_sent
                            network_data = '~nc=1'
                            for i_networks in range(len(l.network_names)):
                                network_data += '~ns=' + Webifi.tilde_encode_data(l.network_names[i_networks])
                            network_data += l.constants.terminating_string
                            try:
                                l.websocket.send(network_data)
                                self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                                l.logger.debug('WebSocket: Set network names')
                            except:
                                l.logger.error('WebSocket: failed to Set network names')
                    if not m.last_packet_sent and m.send_packet is not None:
                        # try again with packet that failed previously
                        l.to_cloud_queue.put(m.send_packet)
                        m.waiting_for_response = True
                        m.wait_before_retry = self.get_epoch_time() + l.constants.wait_before_retry_timeout
                        l.logger.debug('Try to send packet again')
                    # check if there is new data to send
                    elif not l.to_master_for_cloud_queue.empty():
                        add_id = True    # id must only be added once
                        send_str = ''
                        to_cloud_packet = WebifiNewInstance()
                        to_cloud_packet.packet_type = l.constants.data_packet
                        to_cloud_packet.url = l.upload_url
                        to_cloud_packet.url_ssl = l.upload_ssl_url
                        to_cloud_packet.page = '/Upload'
                        to_cloud_packet.post_data = ''
                        while not l.to_master_for_cloud_queue.empty() and len(send_str) < l.constants.max_packet_size:
                            if not add_id:
                                # this is not the first message added. check if the next message in the queue is the
                                # same type of message, only one message type is allowed per upload
                                popped_packet = l.to_master_for_cloud_queue.get()
                                if popped_packet is None:
                                    break
                                l.to_master_for_cloud_queue.unshift(popped_packet)
                                if m.send_packet.packet_type != popped_packet.packet_type:
                                    break
                            m.send_packet = l.to_master_for_cloud_queue.get()
                            if m.send_packet is not None:
                                if m.send_packet.packet_type == l.constants.data_packet:
                                    if add_id:
                                        add_id = False
                                        if not l.use_websocket:
                                            to_cloud_packet.post_data += l.upload_params
                                    # add networks
                                    for i in range(len(m.send_packet.to_networks)):
                                        if m.send_packet.to_networks[i] != '':
                                            to_cloud_packet.post_data += '~n=' + m.send_packet.to_networks[i]
                                    # add session IDs
                                    for i in range(len(m.send_packet.to_session_ids)):
                                        if m.send_packet.to_session_ids[i] != '':
                                            to_cloud_packet.post_data += '~s=' + m.send_packet.to_session_ids[i]
                                    # add data type if present
                                    if m.send_packet.data_type != '':
                                        to_cloud_packet.post_data += '~dt=' + m.send_packet.data_type
                                    # add data - must be the last parameter per message
                                    to_cloud_packet.post_data += '~d=' + m.send_packet.data
                                    # see if more packets can be added
                                    while not l.to_master_for_cloud_queue.empty() and len(send_str) < l.constants.max_packet_size:
                                        # make sure that data is going to the same URL before dequeueing it
                                        popped_packet = l.to_master_for_cloud_queue.get()
                                        if popped_packet is not None:
                                            if Webifi.check_if_data_can_be_added(m.send_packet, popped_packet):
                                                # add the data because the data is going to the same devices
                                                to_cloud_packet.post_data += popped_packet.data
                                            else:
                                                # push back to front of queue because parameters are different
                                                l.to_master_for_cloud_queue.unshift(popped_packet)
                                                break
                                        else:
                                            break
                                elif m.send_packet.packet_type == l.constants.cancel_request:
                                    to_cloud_packet = WebifiNewInstance()
                                    to_cloud_packet.packet_type = l.constants.cancel_request
                                    to_cloud_packet.url = l.upload_url
                                    to_cloud_packet.url_ssl = l.upload_ssl_url
                                    to_cloud_packet.post_data = m.send_packet.data
                                    to_cloud_packet.page = '/CancelDownload'
                        m.retry_count = 0
                        if l.use_websocket:
                            to_cloud_packet.post_data += l.constants.terminating_string
                        else:
                            # add counter
                            to_cloud_packet.post_data += '~z=' + str(l.counters.upload)
                        if l.log_level == logging.DEBUG:
                            # log detailed data about the data that was sent
                            log_str = "Data sent: " \
                                      + Webifi.bracket_encode(to_cloud_packet.post_data)
                            l.logger.debug(log_str)
                        if l.use_websocket:
                            try:
                                l.websocket.send(to_cloud_packet.post_data)
                                self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                                l.logger.debug('WebSocket: Sending packet')
                            except:
                                l.logger.error('Exception trying to send data using WebSocket')
                        else:
                            l.to_cloud_queue.put(to_cloud_packet)
                            l.logger.debug('Long Polling: Sending packet')
                        l.counters.upload += 1
                        m.waiting_for_response = True
                        m.wait_before_retry = self.get_epoch_time() + l.constants.wait_before_retry_timeout
            # //////////////////////////////////////////////////////////////////////////////////////////////
            # process data received from web socket
            if not l.websocket_receive_queue.empty():
                wsdict = l.websocket_receive_queue.get()
                if wsdict is not None:
                    something_happened = True
                    response_type_value = Webifi.get_webifi_dictionary_single_value(wsdict, 'rt')
                    ws_error_code = '0'
                    if (response_type_value != 'r') and (response_type_value != 'k'):
                        # receive data does not have an error code
                        ws_error_code = Webifi.get_webifi_dictionary_single_value(wsdict, 'e')
                    if response_type_value == 'a':   # authentication response
                        if ws_error_code == '0':
                            # connection authenticated
                            l.websocket_state = l.constants.ws_state_set_listen_to_networks
                            l.logger.debug('WebSocket connection authenticated')
                            self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                        else:
                            l.logger.debug('WebSocket authentication failed, error code: ' + ws_error_code)
                            l.webifi_state = l.constants.state_request_credentials
                            l.websocket_state = l.constants.ws_state_not_connected
                            try:
                                l.websocket.close()
                            except:
                                l.logger.error('Exception trying to close WebSocket connection')
                        m.waiting_for_response = False
                        self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                        l.keep_alive_sent = False
                    elif response_type_value == 'n':   # set listen to networks response
                        l.networks_updated = True
                        l.websocket_state = l.constants.ws_state_running
                        if ws_error_code == '4':  # New set of networks to which device is listening was set
                            l.logger.debug('All listen to networks was set')
                        elif ws_error_code == '5':  # Not all of the networks to which device is listening was set
                            l.logger.error('Not all listen to networks was set')
                            if l.error_callback is not None:
                                l.error_callback(ws_error_code)
                        elif ws_error_code == '12':  # session id expired
                            l.websocket_state = l.constants.ws_state_not_connected
                            l.webifi_state = l.constants.state_request_credentials
                            l.logger.debug('Session id expired, request credentials again')
                        else:
                            l.logger.error('Error updating networks: ' + ws_error_code)
                            if l.error_callback is not None:
                                l.error_callback(ws_error_code)
                        m.waiting_for_response = False
                        self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                        l.keep_alive_sent = False
                    elif response_type_value == 's':   # send data response
                        send_error = False
                        if ws_error_code == '0':  # success
                            l.logger.debug('Last message sent')
                        elif ws_error_code == '1':  # Unknown error
                            send_error = True
                            l.logger.error('Unknown error sending last message')
                        elif ws_error_code == '2':  # Data could not be sent to one or more recipients
                            send_error = True
                            l.logger.error('Data could not be sent to one or more recipients')
                        elif ws_error_code == '7':  # Protocol error
                            send_error = True
                            l.logger.error('Sending data protocol error')
                        elif ws_error_code == '12':  # expired session id
                            l.websocket_state = l.constants.ws_state_not_connected
                            l.webifi_state = l.constants.state_request_credentials
                            l.logger.error('Sending data, session id expired')
                        elif ws_error_code == '20':  # Could not establish connection to website
                            send_error = True
                            l.logger.error('Could not establish connection to website')
                        else:
                            l.logger.error('Invalid data received from server')
                            ws_error_code = '3'  # Invalid data received from server, please restart service
                            send_error = True
                        if send_error:
                            if l.error_callback is not None:
                                l.error_callback(ws_error_code)
                        m.last_packet_sent = True
                        m.waiting_for_response = False
                        self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                        l.keep_alive_sent = False
                    elif response_type_value == 'r':   # receive data
                        ws_rec_data = DownloadResponse()
                        l.logger.debug('Data received from server')
                        for i_rec_data in range(1,  len(wsdict.keys)):
                            if wsdict.keys[i_rec_data] == 'f':  # from session id
                                ws_rec_data.from_who = int(wsdict.values[i_rec_data])
                            elif wsdict.keys[i_rec_data] == 'dt':  # data type
                                ws_rec_data.data_type = wsdict.values[i_rec_data]
                            elif wsdict.keys[i_rec_data] == 'd':  # data
                                ws_rec_data.data = wsdict.values[i_rec_data]
                                l.from_from_cloud_to_master_queue.put(ws_rec_data)
                                ws_rec_data = DownloadResponse()
                    elif response_type_value == 'k':
                        self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_timeout)
                        l.keep_alive_sent = False
                        l.logger.debug('WebSocket: Keep alive message acknowledged')
                    elif response_type_value == 'c':
                        if ws_error_code == '0':
                            if l.websocket_state == l.constants.ws_state_restart_connection:
                                l.websocket_state = l.constants.ws_state_not_connected
                            else:
                                l.websocket_state = l.constants.ws_state_closing_connection
                            l.websocket.close()
                            m.waiting_for_response = False
                            l.webifi_state = l.constants.state_request_credentials
                            if self.connected:
                                self.connected = False
                                if l.connection_status_callback is not None:
                                    l.connection_status_callback(False)
                            l.logger.info('WebSocket: Stopped the service')
                        else:
                            l.logger.error('WebSocket: Error closing connection')
                            if l.error_callback is not None:
                                l.error_callback(ws_error_code)
            if l.use_websocket:
                if (m.wait_before_retry < self.get_epoch_time()) and \
                        (l.websocket_state == l.constants.ws_state_waiting_for_connection):
                    # connection has timed out, try again
                    something_happened = True
                    l.websocket_state = l.constants.ws_state_not_connected
                    m.waiting_for_response = False
                if (m.wait_before_retry < self.get_epoch_time()) and \
                        (l.websocket_state == l.constants.ws_state_connected_auth_sent):
                    # authorisation sent but has timed out, send it again
                    something_happened = True
                    l.websocket_state = l.constants.ws_state_connected_not_auth
                    m.waiting_for_response = False
                    l.logger.debug('WebSocket: Auth timed out, trying again')
                if (m.wait_before_retry < self.get_epoch_time()) and \
                        (l.websocket_state == l.constants.ws_state_set_listen_to_networks_sent):
                    # no response when setting networks, try again
                    something_happened = True
                    m.waiting_for_response = False
                    l.websocket_state = l.constants.ws_state_set_listen_to_networks
                    l.logger.debug('WebSocket: Setting networks timed out, trying again')
                if (l.websocket_state == l.constants.ws_state_running) and \
                        (self.check_if_websocket_keep_alive_expired()):
                    if not l.keep_alive_sent:
                        try:
                            l.websocket.send(l.constants.terminating_string)
                            self.set_new_websocket_keep_alive_timeout(l.constants.websocket_keep_alive_sent_timeout)
                            l.keep_alive_sent = True
                            l.logger.debug('WebSocket: Keep alive message sent')
                        except:
                            l.logger.error('WebSocket: failed to send keep alive')
                    else:
                        # websocket response timed out, connection is dead. Create new connection
                        l.websocket_state = l.constants.ws_state_connection_timeout
                        m.waiting_for_response = False
                        self.set_new_websocket_keep_alive_timeout(l.constants.websocket_thread_dead_timeout)
                        try:
                            l.websocket.keep_running = False
                        except:
                            l.logger.debug('WebSocket: keep_running parameter not supported')
                        try:
                            l.websocket.close()
                        except:
                            l.logger.debug('WebSocket: error closing websocket connection')
                        l.logger.debug('WebSocket: Timeout, restarting connection')

                if (l.websocket_state == l.constants.ws_state_connection_timeout) and \
                    (self.check_if_websocket_keep_alive_expired()):
                    l.logger.debug('WebSocket: WebScoket thread hanged up, create new websocket thread')
                    l.websocket_state = l.constants.ws_state_not_connected
                    l.websocket_thread = threading.Thread(target=self.websocket_thread)
                    l.websocket_thread.start()
            # //////////////////////////////////////////////////////////////////////////////////////////////
            # see if response from toCloud thread
            if not l.from_to_cloud_to_master_queue.empty():
                # parse response from upload request
                d = l.from_to_cloud_to_master_queue.get()
                l.logger.debug('To cloud thread data received')
                if d is not None:
                    something_happened = True
                    m.waiting_for_response = False
                    webifi_dict = Webifi.decode_webifi_protocol(d.response)
                    error_code = Webifi.get_webifi_dictionary_single_value(webifi_dict, 'e')
                    if d.packet_type == l.constants.request_credentials:
                        if error_code == '0':  # success
                            if l.websocket_state == l.constants.ws_state_set_listen_to_networks or l.websocket_state == l.constants.ws_state_running:
                                l.logger.info('Got new credentials but WebSocket is already connected with previous credentials, ignore these credentials')
                            else:
                                l.device_id = Webifi.get_webifi_dictionary_single_value(webifi_dict, 'id')
                                urls = Webifi.get_webifi_dictionary_values(webifi_dict, 'ip')
                                if len(urls) == 2:
                                    if l.constants.use_test_server:
                                        ip_ok = True
                                        ip_ok2 = True
                                    else:
                                        ip_ok = self.test_ip_address(urls[0])
                                        ip_ok2 = self.test_ip_address(urls[1])
                                    if ip_ok and ip_ok2:
                                        l.server_ip_addr = urls[0]
                                        l.server_ip_addr2 = urls[1]
                                        domain_names = Webifi.get_webifi_dictionary_values(webifi_dict, 'dn')
                                        l.upload_ssl_url = domain_names[0]
                                        l.download_ssl_url = domain_names[1]
                                        # extract session ID from device ID
                                        session_id_str = ''
                                        for i in range(len(l.device_id)):
                                            if l.device_id[i] == 's':
                                                # got the whole session ID
                                                l.session_id = int(session_id_str)
                                                break
                                            else:
                                                session_id_str += l.device_id[i]
                                        # store the error codes
                                        store_error_codes = False
                                        l.error_codes = CreateWebifiDictionary()
                                        for ie in range(len(webifi_dict.keys)):
                                            if webifi_dict.keys[ie] == '0':
                                                # this is the first error code
                                                store_error_codes = True
                                            if store_error_codes:
                                                l.error_codes.keys.append(webifi_dict.keys[ie])
                                                l.error_codes.values.append((webifi_dict.values[ie]))
                                        l.webifi_state = l.constants.state_running
                                        self.build_urls()
                                        l.download_thread_request = True  # download thread can start requesting
                                        self.connected = True
                                        l.logger.debug('Got credentials from server')
                                        if l.connection_status_callback is not None:
                                            l.connection_status_callback(True)
                                    else:
                                        l.logger.debug('Error parsing server IP address')
                        elif error_code == '8':  # invalid connect name or password
                            # stop service
                            l.closing_threads = True
                            l.webifi_state = l.constants.state_request_credentials
                            self.connected = False
                            l.download_thread_running = False
                            l.upload_thread_running = False
                            l.master_thread_running = False
                            l.websocket_thread_running = False
                            if l.connection_status_callback is not None:
                                l.connection_status_callback(False)
                            if l.error_callback is not None:
                                l.error_callback(error_code)
                            l.logger.error('Invalid user credentials')
                        elif error_code == '20':  # connection problem
                            if l.error_callback is not None:
                                l.error_callback(error_code)
                            l.logger.debug('Could not connect to server')
                        else:  # protocol error
                            if l.error_callback is not None:
                                l.error_callback('7')
                            l.logger.debug('Protocol error')
                    elif d.packet_type == l.constants.data_packet:
                        send_error = False  # fail immediately if true
                        retry_message = False  # retry message again if we have not reached max retries
                        if error_code == '0':  # success
                            l.logger.debug('Last message sent')
                        elif error_code == '1':  # unknown error
                            retry_message = True
                            l.logger.debug('Unknown error')
                        elif error_code == '2':  # data could not be sent to one or more recipients
                            send_error = True
                            l.logger.debug('Data could not be sent to one or more recipients')
                        elif error_code == '7':  # protocol error
                            retry_message = True
                            l.logger.debug('Protocol error')
                        elif error_code == '12':  # invalid/expired id
                            send_error = True
                            l.webifi_state = l.constants.state_request_credentials
                            l.logger.debug('Expired/invalid session id')
                        elif error_code == '15':  # response to a cancel request
                            if l.closing_threads:
                                l.webifi_state = l.constants.state_request_credentials
                                self.connected = False
                                if l.connection_status_callback is not None:
                                    l.connection_status_callback(False)
                                    l.logger.debug('Stopped the service')
                        elif error_code == '20':  # could not establish connection to website
                            retry_message = True
                            l.logger.debug('Could not establish connection to website')
                        else:
                            error_code = '3'  # invalid data received from server
                            retry_message = True
                            l.logger.debug('Invalid data received from server')
                        if retry_message:
                            if m.retry_count < m.max_retries:
                                m.last_packet_sent = False
                                m.send_packet = m.last_packet_uploaded
                                m.retry_count += 1
                                l.logger.debug('Retrying...')
                            else:
                                m.last_packet_sent = True
                                l.logger.debug('Max retries reached')
                                if l.error_callback is not None:
                                    l.error_callback(error_code)
                        if send_error:
                            l.logger.debug('Send error')
                            if l.error_callback is not None:
                                l.error_callback(error_code)
            # ////////////////////////////////////////////////////////////////////////////////////////////
            # data from FromCloud thread
            if not l.from_from_cloud_to_master_queue.empty():
                d = l.from_from_cloud_to_master_queue.get()
                l.logger.debug('From cloud thread data received')
                if d is not None:
                    something_happened = True
                    if d.error_code == '0':  # no error - data was received
                        if l.discoverable and d.data == '?' and d.data_type == 'Discovery':
                            # send discovery response
                            send_data = CreateSendData()
                            send_data.data_type = "Discovery Response"
                            send_data.data = self.name
                            send_data.to_session_ids.append(str(d.from_who))
                            self.send_data(send_data)
                            l.logger.debug('Discovery response sent')
                        else:
                            d_mes = 'Data received: ' + d.data + ', Data type: ' + d.data_type
                            d_mes += ', From: ' + str(d.from_who)
                            l.logger.debug(d_mes)
                            if l.data_received_callback is not None:
                                l.data_received_callback(d.data, d.data_type, d.from_who)
                    elif d.error_code == '12':     # invalid session id
                        l.webifi_state = l.constants.state_request_credentials
                        l.logger.debug('Invalid session ID from FromCloud thread')
                    # elif '16':   # no data available
                    elif d.error_code == '18':     # multiple download requests made with the same session id
                        l.webifi_state = l.constants.state_request_credentials
                        l.logger.debug('Multiple downloads from same session ID')
                    elif d.error_code == '24':     # download request timeout changed
                        l.logger.debug('Download request timeout changed to: ' + str(l.download_timeout) + ' seconds')

            if not something_happened:
                time.sleep(l.constants.thread_sleep_time)
        l.master_thread_terminated = True
        l.logger.debug('Master thread terminated')

    def upload_thread(self):
        """This function must never be called directly by user. Call Start() to start the service
        :return:
        """
        l = self.__locals
        l.upload_thread_running = True
        l.upload_thread_terminated = False
        l.logger.debug('Upload thread started')
        while l.upload_thread_running:
            if not l.to_cloud_queue.empty():
                try:
                    packet = l.to_cloud_queue.get()
                    l.master_vars.last_packet_uploaded = packet
                    if l.use_encryption:
                        where = packet.url_ssl
                        if l.ssl_context_upload is None:
                            l.ssl_context_upload = ssl.create_default_context()
                        con = http.client.HTTPSConnection(where, 443, context=l.ssl_context_upload)
                    else:
                        where = packet.url
                        con = http.client.HTTPConnection(where)
                    upload_response = UploadResponse()
                    con.request('POST', packet.page, packet.post_data, l.headers)
                    response = con.getresponse()
                    l.logger.debug('Upload request sent')
                    upload_response.packet_type = packet.packet_type
                    if response.status == 200:
                        upload_response.response = response.read()
                    else:
                        upload_response.response = '~e=20'  # Could not establish connection to website
                except:
                    upload_response.response = '~e=20'  # Could not establish connection to website
                l.from_to_cloud_to_master_queue.put(upload_response)
            else:
                time.sleep(self.__locals.constants.thread_sleep_time)
        l.upload_thread_terminated = True
        l.logger.debug('Upload thread terminated')

    def download_thread(self):
        """This function must never be called directly by user. Call Start() to start the service
        :return:
        """
        l = self.__locals
        l.download_thread_running = True
        l.download_thread_terminated = False
        l.restart_download = False
        l.last_download_successful = False
        download_started_time = self.get_epoch_time()
        l.logger.debug('Download thread started')
        while l.download_thread_running:
            if l.use_websocket:
                # this thread must not do anything if we use websocket
                time.sleep(0.2)
            else:
                wait_before_next_request = False
                if l.webifi_state == l.constants.state_running:
                    url = ''
                    previous_download_started_time = download_started_time
                    download_started_time = self.get_epoch_time()
                    try:
                        if l.use_encryption:
                            url += l.download_ssl_url
                            if l.ssl_context_download is None:
                                l.ssl_context_download = ssl.create_default_context()
                            con = http.client.HTTPSConnection(url, 443, context=l.ssl_context_download, timeout=l.download_timeout+30)
                        else:
                            url += l.download_url
                            con = http.client.HTTPConnection(url, timeout=l.download_timeout+30)
                        post_data = l.auth_params
                        update_networks = False
                        if not l.networks_updated:
                            for i in range(len(l.network_names)):
                                post_data += '~n=' + Webifi.tilde_encode_data(l.network_names[i])
                            update_networks = True
                        else:
                            if l.download_timeout != l.constants.default_download_request_timeout:
                                post_data += '~t=' + str(l.download_timeout)
                            if l.restart_download:
                                l.restart_download = False
                                post_data += '~r=1'
                        post_data += '~z=' + str(l.counters.download)
                        if update_networks:
                            l.logger.debug('Update default networks started (' + str(l.counters.download) + ')')
                        else:
                            l.logger.debug('New download request started (' + str(l.counters.download) + ')')
                        l.counters.download += 1
                        con.request('POST', l.download_page, post_data, l.headers)
                        response = con.getresponse()
                        l.logger.debug('Download response received')
                        if response.status == 200:
                            temp_resp = response.read()
                            webifi_dict = Webifi.decode_webifi_protocol(temp_resp)
                            error_code = Webifi.get_webifi_dictionary_single_value(webifi_dict, 'e')
                            if error_code is None:
                                l.wait_before_next_request = True
                            else:
                                if error_code == '0':
                                    d = DownloadResponse()
                                    for i in range(len(webifi_dict.keys)):
                                        if webifi_dict.keys[i] == 'f':  # from session id
                                            d.from_who = int(webifi_dict.values[i])
                                        elif webifi_dict.keys[i] == 'dt':  # data type
                                            d.data_type = webifi_dict.values[i]
                                        elif webifi_dict.keys[i] == 'd':  # data
                                            d.data = webifi_dict.values[i]
                                            l.from_from_cloud_to_master_queue.put(d)
                                            d = DownloadResponse()
                                    l.last_download_successful = True
                                elif error_code == '1':  # unknown error
                                    l.logger.debug('Download error - Unknown error')
                                    l.wait_before_next_request = True
                                elif error_code == '4':  # new set of networks to which device is listening was set
                                    l.networks_updated = True
                                    l.logger.debug('All listen to networks was set')
                                    l.last_download_successful = True
                                elif error_code == '5':  # not all of the networks to which device is listening was set
                                    l.networks_updated = True
                                    l.logger.debug('Not all listen to networks was set')
                                    if l.error_callback is not None:
                                        l.error_callback(error_code)
                                    l.last_download_successful = True
                                elif error_code == '7':  # protocol error
                                    l.logger.debug('Download error - Protocol error')
                                    l.wait_before_next_request = True
                                    l.last_download_successful = True
                                elif error_code == '12':  # invalid/expired id
                                    d = DownloadResponse()
                                    d.error_code = error_code
                                    l.from_from_cloud_to_master_queue.put(d)
                                    l.logger.debug('Download error - Session ID expired')
                                    l.wait_before_next_request = True
                                    l.last_download_successful = True
                                    l.webifi_state = l.constants.state_request_credentials
                                elif error_code == '15':  # download request cancelled by user
                                    l.logger.debug('Download cancelled by user')
                                    l.last_download_successful = True
                                    if l.set_use_websocket:
                                        l.set_use_websocket = False
                                        l.use_websocket = True
                                elif error_code == '16':  # no data available - restart connection immediately
                                    l.last_download_successful = True
                                elif error_code == '18':  # multiple download requests made with the same session ID
                                    # there are devices on the internet that will send the same request to the server again
                                    # without us knowing about it. This will cause a duplicate request error.
                                    # if the request is older than 5 seconds then this is what happened. Calculate the time
                                    # it took and make sure that the request time is shorter than this
                                    l.logger.debug('Multiple requests to same session ID')
                                    current_time = self.get_epoch_time()
                                    if l.last_download_successful:
                                        delta_t = current_time - download_started_time
                                    else:
                                        delta_t = current_time - previous_download_started_time
                                    check_time = l.constants.minimum_download_threshold_time
                                    if not l.last_download_successful:
                                        # the download request waited before making a new request - account for that
                                        check_time += l.constants.download_error_wait_time
                                        check_time += l.constants.download_slippage_time
                                    if delta_t >= 5:
                                        delta_t -= l.constants.download_decrease_time
                                        delta_t -= l.constants.download_slippage_time
                                        if not l.last_download_successful:
                                            # the download thread waited for 5 seconds before starting a new request
                                            # subtract that as well
                                            delta_t -= l.constants.minimum_download_threshold_time
                                        if delta_t < l.constants.minimum_download_timeout:
                                            delta_t = l.constants.minimum_download_timeout
                                        if delta_t <= l.download_timeout:
                                            l.download_timeout = int(delta_t)
                                            d = DownloadResponse()
                                            d.error_code = '24'
                                            l.restart_download = True
                                            l.from_from_cloud_to_master_queue.put(d)
                                    else:
                                        d = DownloadResponse()
                                        d.error_code = error_code
                                        l.from_from_cloud_to_master_queue.put(d)
                                    l.last_download_successful = True
                    except:
                        wait_before_next_request = True
                        l.last_download_successful = False
                if wait_before_next_request:
                    time.sleep(5)
                else:
                    time.sleep(0.1)
        l.download_thread_terminated = True
        l.logger.debug('Download thread terminated')

    def build_urls(self):
        """This function must never be called directly by user. Call Start() to start the service
        :return:
        """
        l = self.__locals
        # build download parameters
        l.download_url = l.server_ip_addr2
        l.download_page = '/Download'
        l.auth_params = '~id=' + l.device_id
        # build upload url
        l.upload_url = l.server_ip_addr
        l.upload_page = '/Upload'
        l.upload_params = '~id=' + l.device_id
        # build websocket urls
        l.websocket_url = 'ws://' + l.upload_url + '/api/WebSocket'
        l.websocket_ssl_url = 'wss://' + l.upload_ssl_url + '/api/WebSocket'

    def send_cancel_request(self, terminate_session=False):
        """This function must never be called directly by user. Call Start() to start the service
        :param terminate_session: If this value is set to true then the server will terminate the session for this
        device. A new session has to be started if the device needs to connect again.
        :return:
        """
        l = self.__locals
        if l.webifi_state != l.constants.state_request_credentials:  # service is running
            send_packet = CloudSendPacket()
            send_packet.url = l.server_ip_addr
            send_packet.url_ssl = l.upload_ssl_url
            send_packet.page = '/CancelDownload'
            post_str = '~id=' + l.device_id
            if terminate_session:
                post_str += '~ts=1'
                l.closing_threads = True
            send_packet.data = post_str
            send_packet.packet_type = l.constants.cancel_request
            l.to_master_for_cloud_queue.put(send_packet)
            l.logger.debug('Download cancel request sent to server')

    def close_connection(self, clear_callbacks=False):
        """ Must be called when service is stopped. This will close all the connections and threads
        :param clear_callbacks: Set to true to clear all the callback. This is useful when this function
        is called from the window close event. Any callback called with generate an error.
        """
        l = self.__locals
        if clear_callbacks:
            l.data_received_callback = None
            l.connection_status_callback = None
            l.error_callback = None
        l.closing_threads = True
        if l.download_thread_running:  #check if threads are running
            l.download_thread_running = False
            if l.webifi_state == l.constants.state_running:
                if l.use_websocket:
                    try:
                        l.websocket.send('~c=t' + l.constants.terminating_string)  # send websocket termination message
                        l.websocket_state = l.constants.ws_state_closing_connection
                        l.logger.debug('WebSocket: Close connection message sent')
                    except Exception as inst:
                        l.logger.error('Error closing WebSocket connection: ' + inst)
                        l.websocket_state = l.constants.ws_state_not_connected
                else:
                    self.send_cancel_request(True)
                    l.logger.debug('Long polling: Close connection message sent')
            l.download_thread.join()
            l.upload_thread_running = False
            l.upload_thread.join()
            l.websocket_thread_running = False
            l.websocket_thread.join()
            l.master_thread_running = False
            l.master_thread.join()
            if self.connected:
                self.connected = False
                if l.connection_status_callback is not None:
                    l.connection_status_callback(False)

    def convert_error_code_to_string(self, error_code):
        """Return a string with the description for an error code
        :param error_code: The error code, for example: 0
        :return: The description of the error
        """
        if self.__locals.error_codes is None:
            return error_code
        if type(error_code) is int:
            error_code_num = str(error_code)
        elif type(error_code) is str:
            error_code_num = error_code
        else:
            return error_code
        error_str = Webifi.get_webifi_dictionary_single_value(self.__locals.error_codes, error_code_num)
        if error_str is None:
            error_str = 'Check https://www.webifi.me/error-codes/ for error codes'
        return error_str

    @staticmethod
    def get_webifi_dictionary_values(webifi_dict, key):
        """Search the dictionary and return an array of values that matched the key
        :param webifi_dict: Dictionary to be searched
        :param key: Key to look for in dictionary
        :return: An array of values that matched the key
        """
        values = []
        for i in range(len(webifi_dict.keys)):
            if webifi_dict.keys[i] == key:
                values.append(webifi_dict.values[i])
        return values

    @staticmethod
    def get_webifi_dictionary_single_value(webifi_dict, key):
        """Search the dictionary and return the first value that matches the key
        :param webifi_dict: Dictionary to be searched
        :param key: First key to look for in dictionary
        :return: The value of the first key that matches, otherwise None
        """
        value = None
        for i in range(len(webifi_dict.keys)):
            if webifi_dict.keys[i] == key:
                # found first key that matched
                value = webifi_dict.values[i]
                break
        return value

    @staticmethod
    def tilde_encode_data(data):
        """Tilde is the control character used by Webifi. This function will encode the tilde character
        and the character for ASCII 0
        :param data: The data that must be encoded
        :return: The encoded data
        """
        encoded = ''
        for i in range(0, len(data)):
            if data[i] == '~':
                encoded += '~~'
            elif ord(data[i]) == 0:
                encoded += '~-'
            else:
                encoded += data[i]
        return encoded

    @staticmethod
    def encode_webifi_protocol(webifi_dict):
        """Will generate an output string based on a webifi dictionary. The values will be tilde encoded
        :param webifi_dict: Input webifi dictionary
        :return: The output string
        """
        encoded_data = ''
        for i in range(0, len(webifi_dict.keys)):
            encoded_data += '~' + webifi_dict.keys[i] + '=' + Webifi.tilde_encode_data(webifi_dict.values[i])
        return encoded_data

    @staticmethod
    def decode_webifi_protocol(rawdata):
        """This function will decode the Webifi protocol where a tilde is used as a control character
        :param rawdata: Raw data received from the server
        :return: Return a Webifi dictionary with all the decoded data
        """
        webifi_dict = CreateWebifiDictionary()
        state_key = 0
        state_value = 1
        state_control_char_in_value = 2
        state = state_key
        the_key = ''
        the_value = ''
        control_char = '~'
        end_of_key = '='

        # convert byte array to string
        data_type = type(rawdata)
        if data_type == str:
            data = rawdata
        else:
            data = ''
            for b in rawdata:
                data += chr(b)

        if data[0] != '~':
            return   # protocol problem
        for i in range(1, len(data)):
            c = data[i]
            last_char = False
            if i == len(data) - 1:
                last_char = True
            if state == state_key:
                if last_char or c == control_char:
                    return webifi_dict
                if c == end_of_key:
                    state = state_value
                else:
                    the_key += c
            elif state == state_value:
                if c == control_char:
                    if last_char:
                        return   # last character cannot be a control character
                    else:
                        state = state_control_char_in_value
                else:
                    the_value += c
                    if last_char:
                        webifi_dict.keys.append(the_key)
                        webifi_dict.values.append(the_value)
            elif state == state_control_char_in_value:
                if c == control_char:
                    # double tilde means a tilde was sent
                    the_value += c
                    state = state_value
                    if last_char:
                        webifi_dict.keys.append(the_key)
                        webifi_dict.values.append(the_value)
                elif c == '-':
                    # this means a zero was sent in the string
                    the_value += chr(0)
                    state = state_value
                    if last_char:
                        webifi_dict.keys.append(the_key)
                        webifi_dict.values.append(the_value)
                else:
                    if last_char:
                        return   # last character cannot be a control character
                    else:
                        webifi_dict.keys.append(the_key)
                        webifi_dict.values.append(the_value)
                        the_key = ''
                        the_value = ''
                        the_key += c
                        state = state_key
        return webifi_dict

    def send_discovery(self, to_networks=None):
        send_data = CreateSendData()
        if to_networks is not None:
            send_data.to_networks = to_networks
        send_data.data_type = 'Discovery'
        send_data.data = '?'
        self.send_data(send_data)

    def get_buffered_amount(self):
        return self.__locals.to_master_for_cloud_queue.get_size()

    def set_new_websocket_keep_alive_timeout(self, seconds_from_now):
        self.tick_websocket_keep_alive = self.get_epoch_time() + seconds_from_now

    def check_if_websocket_keep_alive_expired(self):
        if self.tick_websocket_keep_alive < self.get_epoch_time():
            return True  # expired
        return False

    def websocket_onopen(self, ws):
        l = self.__locals
        l.logger.debug('WebSocket onopen event')
        l.websocket_state = l.constants.ws_state_connected_not_auth

    def websocket_onclose(self, ws):
        l = self.__locals
        l.logger.debug('WebSocket onclose event')
        if l.websocket_state != l.constants.ws_state_waiting_for_connection:  # connection has already been restarted
            l.websocket_state = l.constants.ws_state_not_connected

    def websocket_onerror(self, ws, error):
        l = self.__locals
        l.logger.debug('WebSocket onerror event: ' + error.strerror)
        # restart connection on websocket error
        l.websocket_state = l.constants.ws_state_not_connected
        l.websocket.close()
        l.webifi_state = l.constants.state_request_credentials

    def websocket_onmessage(self, ws, message):
        l = self.__locals
        l.logger.debug('WebSocket onmessage event')
        # convert byte array to string
        data = ''
        for b in message:
            data += chr(b)
        if l.log_level == logging.DEBUG:
            # log detailed data about the data that was received
            log_str = "WebSocket onmessage event, data received: " \
                      + Webifi.bracket_encode(data)
            l.logger.debug(log_str)
        l.websocket_rec_data_buf += data
        while self.process_websocket_rec_data():
            pass

    def websocket_thread(self):
        """This function must never be called directly by user. Call Start() to start the service
        :return:
        """
        l = self.__locals
        l.websocket_thread_running = True
        l.websocket_thread_terminated = False
        l.logger.info('WebSocket thread started')
        while l.websocket_thread_running:
            if not l.use_websocket:
                time.sleep(0.2)  # this thread must not do anything when long polling is used
            else:
                if l.webifi_state == l.constants.state_running:
                    if l.websocket_state == l.constants.ws_state_not_connected:
                        try:
                            # websocket.enableTrace(True)
                            l.logger.debug('Create WebSocket connection')
                            if l.use_encryption:
                                connect_str = l.websocket_ssl_url
                            else:
                                connect_str = l.websocket_url
                            l.websocket = websocket.WebSocketApp(connect_str,
                                            on_message = self.websocket_onmessage,
                                            on_error = self.websocket_onerror,
                                            on_close = self.websocket_onclose)
                            l.websocket.on_open = self.websocket_onopen
                            l.websocket.run_forever()
                            l.logger.debug('WebSocket connection returned')
                            if l.websocket_state != l.constants.ws_state_not_connected:
                                l.websocket_state = l.constants.ws_state_waiting_for_connection
                        except:
                            l.logger.debug('Error opening WebSocket connection')
                            time.sleep(1)
            time.sleep(0.1)
        l.websocket_thread_terminated = True
        l.logger.debug('WebSocket thread terminated')

    def process_websocket_rec_data(self):
        l = self.__locals
        try:
            terminating_tag_index = l.websocket_rec_data_buf.index(l.constants.terminating_string)
            # at least one complete message was received
            terminating_tag_index += 4  # add size of terminating tag
            new_message = l.websocket_rec_data_buf[:terminating_tag_index]
            l.websocket_rec_data_buf = l.websocket_rec_data_buf[terminating_tag_index:] # remove received part
            dict = Webifi.decode_webifi_protocol(new_message)
            l.websocket_receive_queue.put(dict)
        except:
            return False
        return True