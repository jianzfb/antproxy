#!/usr/bin/env python3
# coding=utf-8
from antproxy.common_func import *
import queue
import atexit

_listening_sockets = collections.deque() # for close at exit
__author__ = "Aploium <i@z.codes>"
__website__ = "https://github.com/aploium/shootback"


@atexit.register
def close_listening_socket_at_exit():
    log.info("exiting...")
    global _listening_sockets

    cc = len(_listening_sockets)
    while cc:
        s = _listening_sockets.popleft()
        cc -= 1
        try:
            log.info("closing: {}".format(s))
            s.shutdown()
            s.close()
        except:
            pass


def try_bind_port(sock, addr):
    while True:
        try:
            sock.bind(addr)
        except Exception as e:
            log.error(("unable to bind {}, {}. If this port was used by the recently-closed shootback itself\n"
                       "then don't worry, it would be available in several seconds\n"
                       "we'll keep trying....").format(addr, e))
            log.debug(traceback.format_exc())
            time.sleep(3)
        else:
            break


class StoppableThread(threading.Thread):
    def __init__(self, thread_name, params, func):
        super(StoppableThread, self).__init__()
        self._stop_evt = threading.Event()
        self.daemon = True
        self.name = thread_name
        self.func = func
        self.params = params
    
    def stop(self):
        self._stop_evt.set()
    
    def run(self):
        self.func(self.params, self._stop_evt)
    
    
class Master:
    def __init__(self, working_pool=None):
        """

        :param customer_listen_addr: equals to the -c/--customer param
        :param communicate_addr: equals to the -m/--master param
        """
        self.thread_pool = {}
        self.thread_pool["spare_slaver"] = {}
        self.thread_pool["working_slaver"] = {}
        
        self.working_pool = working_pool or {}

        self.socket_bridge = SocketBridge()

        # a queue for customers who have connected to us,
        #   but not assigned a slaver yet
        self.pending_customers = queue.Queue()

        self.external_slaver = False
        self.slaver_pool = collections.deque()

        # prepare Thread obj, not activated yet
        self.thread_pool["heart_beat_daemon"] = threading.Thread(
            target=self._heart_beat_daemon,
            name="heart_beat_daemon-{}".format('server'),
            daemon=True,
        )

        # prepare assign_slaver_daemon
        self.thread_pool["assign_slaver_daemon"] = threading.Thread(
            target=self._assign_slaver_daemon,
            name="assign_slaver_daemon-{}".format('server'),
            daemon=True,
        )
      
        self.customer_slaver_map = {}
    
    def add_proxy_server(self, customer_listen_addr, communicate_addr):
        _fmt_communicate_addr = fmt_addr(communicate_addr)
        
        # # event
        # self.stoppable_thread_events["listen_slaver-{}".format(_fmt_communicate_addr)] = threading.Event()
        # # thread
        # self.thread_pool["listen_slaver-{}".format(_fmt_communicate_addr)] = threading.Thread(
        #     target=self._listen_slaver,
        #     args=(communicate_addr,self.stoppable_thread_events["listen_slaver-{}".format(_fmt_communicate_addr)]),
        #     name="listen_slaver-{}".format(_fmt_communicate_addr),
        #     daemon=True,
        # )
        self.thread_pool["listen_slaver-{}".format(_fmt_communicate_addr)] = \
            StoppableThread("listen_slaver-{}".format(_fmt_communicate_addr), communicate_addr, self._listen_slaver)
        self.thread_pool["listen_slaver-{}".format(_fmt_communicate_addr)].start()
        
        # # event
        # self.stoppable_thread_events["listen_customer-{}".format(_fmt_communicate_addr)] = threading.Event()
        # # thread
        # self.customer_listen_addr = customer_listen_addr
        # self.thread_pool["listen_customer-{}".format(_fmt_communicate_addr)] = threading.Thread(
        #     target=self._listen_customer,
        #     args=(customer_listen_addr, self.stoppable_thread_events["listen_customer-{}".format(_fmt_communicate_addr)]),
        #     name="listen_customer-{}".format(_fmt_communicate_addr),
        #     daemon=True,
        # )
        self.thread_pool["listen_customer-{}".format(_fmt_communicate_addr)] = \
            StoppableThread("listen_customer-{}".format(_fmt_communicate_addr),customer_listen_addr , self._listen_customer)
        self.thread_pool["listen_customer-{}".format(_fmt_communicate_addr)].start()
        self.customer_slaver_map[customer_listen_addr[1]] = communicate_addr[1]
    
    def delete_proxy_server(self, customer_listen_addr, communicate_addr):
        global _listening_sockets
        _fmt_communicate_addr = fmt_addr(communicate_addr)

        # 1.step stop listen slaver and listen customer thread
        if "listen_slaver-{}".format(_fmt_communicate_addr) in self.thread_pool:
            self.thread_pool["listen_slaver-{}".format(_fmt_communicate_addr)].stop()
            del self.thread_pool["listen_slaver-{}".format(_fmt_communicate_addr)]

        if "listen_customer-{}".format(_fmt_communicate_addr) in self.thread_pool:
            self.thread_pool["listen_customer-{}".format(_fmt_communicate_addr)].stop()
            del self.thread_pool["listen_customer-{}".format(_fmt_communicate_addr)]

        # 2.step delete _listening_sockets record
        cc = len(_listening_sockets)
        while cc:
            s = _listening_sockets.popleft()
            cc -= 1
            if s.getsockname()[1] in [customer_listen_addr[1], communicate_addr[1]]:
                pass
            else:
                _listening_sockets.append(s)
    
    def start(self):
        self.thread_pool["heart_beat_daemon"].start()
        self.thread_pool["assign_slaver_daemon"].start()
        self.thread_pool["socket_bridge"] = self.socket_bridge.start_as_daemon()

    def _transfer_complete(self, addr_customer):
        """a callback for SocketBridge, do some cleanup jobs"""
        log.info("customer complete: {}".format(addr_customer))
        del self.working_pool[addr_customer]

    def _serve_customer(self, conn_customer, conn_slaver):
        """put customer and slaver sockets into SocketBridge, let them exchange data"""
        self.socket_bridge.add_conn_pair(
            conn_customer, conn_slaver,
            functools.partial(  # it's a callback
                # 这个回调用来在传输完成后删除工作池中对应记录
                self._transfer_complete,
                conn_customer.getpeername()
            )
        )

    @staticmethod
    def _send_heartbeat(conn_slaver):
        """send and verify heartbeat pkg"""
        conn_slaver.send(CtrlPkg.pbuild_heart_beat().raw)

        pkg, verify = CtrlPkg.recv(
            conn_slaver, expect_ptype=CtrlPkg.PTYPE_HEART_BEAT)  # type: CtrlPkg,bool

        if not verify:
            return False

        if pkg.prgm_ver < 0x000B:
            # shootback before 2.2.5-r10 use two-way heartbeat
            #   so there is no third pkg to send
            pass
        else:
            # newer version use TCP-like 3-way heartbeat
            #   the older 2-way heartbeat can't only ensure the
            #   master --> slaver pathway is OK, but the reverse
            #   communicate may down. So we need a TCP-like 3-way
            #   heartbeat
            conn_slaver.send(CtrlPkg.pbuild_heart_beat().raw)

        return verify

    def _heart_beat_daemon(self):
        """

        每次取出slaver队列头部的一个, 测试心跳, 并把它放回尾部.
            slaver若超过 SPARE_SLAVER_TTL 秒未收到心跳, 则会自动重连
            所以睡眠间隔(delay)满足   delay * slaver总数  < TTL
            使得一轮循环的时间小于TTL,
            保证每个slaver都在过期前能被心跳保活
        """
        default_delay = 5 + SPARE_SLAVER_TTL // 12
        delay = default_delay
        log.info("heart beat daemon start, delay: {}s".format(delay))
        while True:
            time.sleep(delay)
            # log.debug("heart_beat_daemon: hello! im weak")

            # ---------------------- preparation -----------------------
            slaver_count = len(self.slaver_pool)
            if not slaver_count:
                log.warning("heart_beat_daemon: sorry, no slaver available, keep sleeping")
                # restore default delay if there is no slaver
                delay = default_delay
                continue
            else:
                # notice this `slaver_count*2 + 1`
                # slaver will expire and re-connect if didn't receive
                #   heartbeat pkg after SPARE_SLAVER_TTL seconds.
                # set delay to be short enough to let every slaver receive heartbeat
                #   before expire
                delay = 1 + SPARE_SLAVER_TTL // max(slaver_count * 2 + 1, 12)

            # pop the oldest slaver
            #   heartbeat it and then put it to the end of queue
            slaver = self.slaver_pool.popleft()
            addr_slaver = slaver["addr_slaver"]

            # ------------------ real heartbeat begin --------------------
            start_time = time.perf_counter()
            try:
                hb_result = self._send_heartbeat(slaver["conn_slaver"])
            except Exception as e:
                log.warning("error during heartbeat to {}: {}".format(
                    fmt_addr(addr_slaver), e))
                log.debug(traceback.format_exc())
                hb_result = False
            finally:
                time_used = round((time.perf_counter() - start_time) * 1000.0, 2)
            # ------------------ real heartbeat end ----------------------

            if not hb_result:
                log.warning("heart beat failed: {}, time: {}ms".format(
                    fmt_addr(addr_slaver), time_used))
                try_close(slaver["conn_slaver"])
                del slaver["conn_slaver"]

                # if heartbeat failed, start the next heartbeat immediately
                #   because in most cases, all 5 slaver connection will
                #   fall and re-connect in the same time
                delay = 0
            else:
                log.debug("heartbeat success: {}, time: {}ms".format(
                    fmt_addr(addr_slaver), time_used))
                self.slaver_pool.append(slaver)

    @staticmethod
    def _handshake(conn_slaver):
        """
        handshake before real data transfer
        it ensures:
            1. client is alive and ready for transmission
            2. client is shootback_slaver, not mistakenly connected other program
            3. verify the SECRET_KEY
            4. tell slaver it's time to connect target

        handshake procedure:
            1. master hello --> slaver
            2. slaver verify master's hello
            3. slaver hello --> master
            4. (immediately after 3) slaver connect to target
            4. master verify slaver
            5. enter real data transfer
        """
        conn_slaver.send(CtrlPkg.pbuild_hs_m2s().raw)

        buff = select_recv(conn_slaver, CtrlPkg.PACKAGE_SIZE, 2)
        if buff is None:
            return False

        pkg, verify = CtrlPkg.decode_verify(buff, CtrlPkg.PTYPE_HS_S2M)  # type: CtrlPkg,bool

        log.debug("CtrlPkg from slaver {}: {}".format(conn_slaver.getpeername(), pkg))

        return verify

    def _get_an_active_slaver(self, match_flag):
        """get and activate an slaver for data transfer"""
        try_count = 100
        
        while True:
            try:
                dict_slaver = None
                
                cc = len(self.slaver_pool)
                while cc:
                    check_matched_slaver = self.slaver_pool.popleft()
                    if check_matched_slaver["conn_slaver"].getsockname()[1] != match_flag:
                        cc -= 1
                        self.slaver_pool.append(check_matched_slaver)
                        continue
                    else:
                        dict_slaver = check_matched_slaver
                        break
                
                if dict_slaver is None:
                    raise EOFError
            except:
                if try_count:
                    time.sleep(0.02)
                    try_count -= 1
                    if try_count % 10 == 0:
                        log.error("!!NO SLAVER AVAILABLE!!  trying {}".format(try_count))
                    continue
                return None

            conn_slaver = dict_slaver["conn_slaver"]

            try:
                hs = self._handshake(conn_slaver)
            except Exception as e:
                log.warning("Handshake failed: {}".format(e))
                log.debug(traceback.format_exc())
                hs = False

            if hs:
                return conn_slaver
            else:
                log.warning("slaver handshake failed: {}".format(dict_slaver["addr_slaver"]))
                try_close(conn_slaver)

                time.sleep(0.02)

    def _assign_slaver_daemon(self):
        """assign slaver for customer"""
        while True:
            # get a newly connected customer
            conn_customer, addr_customer = self.pending_customers.get()
            
            conn_slaver = self._get_an_active_slaver(self.customer_slaver_map[conn_customer.getsockname()[1]])
            if conn_slaver is None:
                log.warning("Closing customer[{}] because no available slaver found".format(
                    addr_customer))

                # finding thread with conn_customer
                mm = conn_customer.getsockname()
                if "listen_customer-{}".format(fmt_addr((mm[0], mm[1]+1))) in self.thread_pool:
                    self.thread_pool["listen_customer-{}".format(fmt_addr((mm[0], mm[1]+1)))].stop()
                    self.thread_pool.pop("listen_customer-{}".format(fmt_addr((mm[0], mm[1]+1))))
                if "listen_slaver-{}".format(fmt_addr((mm[0], mm[1]+1))) in self.thread_pool:
                    self.thread_pool["listen_slaver-{}".format(fmt_addr((mm[0], mm[1]+1)))].stop()
                    self.thread_pool.pop("listen_slaver-{}".format(fmt_addr((mm[0], mm[1]+1))))

                try_close(conn_customer)
                continue
            else:
                log.debug("Using slaver: {} for {}".format(conn_slaver.getpeername(), addr_customer))

            self.working_pool[addr_customer] = {
                "addr_customer": addr_customer,
                "conn_customer": conn_customer,
                "conn_slaver": conn_slaver,
            }

            try:
                self._serve_customer(conn_customer, conn_slaver)
            except:
                try:
                    try_close(conn_customer)
                except:
                    pass
                continue

    def _listen_slaver(self, communicate_addr, stop_event):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try_bind_port(sock, communicate_addr)
        sock.listen(10)
        sock.settimeout(5)     # unit second
        _listening_sockets.append(sock)
        log.info("Listening for slavers: {}".format(fmt_addr(communicate_addr)))
        while not stop_event.isSet():
            try:
                conn, addr = sock.accept()
            except:
                # ignore time out error
                continue
            self.slaver_pool.append({
                "addr_slaver": addr,
                "conn_slaver": conn,
            })
            log.info("Got slaver {} Total: {}".format(
                fmt_addr(addr), len(self.slaver_pool)
            ))

        # close socket
        try:
            # sock.shutdown(2)
            sock.close()
        except:
            pass

        log.info("stop listening for slavers: {}".format(fmt_addr(communicate_addr)))
        
    def _listen_customer(self, customer_listen_addr, stop_event):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try_bind_port(sock, customer_listen_addr)
        sock.listen(20)
        sock.settimeout(5)     # unit second
        _listening_sockets.append(sock)
        log.info("Listening for customers: {}".format(
            fmt_addr(customer_listen_addr)))
        while not stop_event.isSet():
            try:
                conn_customer, addr_customer = sock.accept()
            except:
                # ignore time out error
                continue
              

            log.info("Serving customer: {} Total customers: {}".format(
                addr_customer, self.pending_customers.qsize() + 1
            ))

            # just put it into the queue,
            #   let _assign_slaver_daemon() do the else
            #   don't block this loop

            self.pending_customers.put((conn_customer, addr_customer))

        # close socket
        try:
            # sock.shutdown(2)
            sock.close()
        except:
            pass

        log.info("stop listening for customer: {}".format(fmt_addr(customer_listen_addr)))


def launch_master_proxy():
    global SPARE_SLAVER_TTL
    global SECRET_KEY
    
    SECRET_KEY = "shootback"
    CtrlPkg.recalc_crc32()
    
    SPARE_SLAVER_TTL = 300
    configure_logging(logging.INFO)
    
    # run_master(communicate_addr, customer_listen_addr)
    master_proxy = Master()
    master_proxy.start()

    return master_proxy
