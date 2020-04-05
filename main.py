import math
import random
import cProfile
import csv

# converted to slots
node_count = 1000
frame_size = 50*8                   # bits
ACK_size = 30*8                       # bits
RTS_size = 30*8                       # bits
CTS_size = 30*8                       # bits
SIFS_length = 1                       # slots
DIFS_length = 2                       # slots
traffic_rate = 60                    # bits per slot (3Mbps)
CW0 = 4                               # slots
CWmax = 1024                          # slots
SIM_TIME_SECONDS = 100
global_duration = SIM_TIME_SECONDS*10**6/20         # slots
frame_transmission_time = frame_size/traffic_rate  # 133 microsec
ACK_transmission_time = 30*8/120      # = 2 slot
# Note: SIFS is handled by adding 1 to ACK transmission time below.
MIN_ARRIVAL_RATE = 1  # frames/s
MAX_ARRIVAL_RATE = 5


class channel:
    def __init__(self):
        self.status = 'idle'

    def set_status(self, status):
        self.status = status


class station:
    def __init__(self, name, traffic_rate):
        self.name = name
        self.traffic_rate = traffic_rate
        self.status = 'waiting'
        # possible statuses: waiting, DIFS, backoff, transmission
        self.CW = CW0

        self.backlog = []
        self.frames_transmitted = 0
        self.next_arrival_in = 0
        self.DIFS_timer = 0
        self.backoff_timer = 0
        self.transmission_timer = 0

        self.delay_list = []

        self.occupation_timer_status = 'off'
        self.occupied_slots_count = 0

        self.total_frames_gen = 0
        self.collision_count = 0
        self.total_frames_dropped = 0

    def backlog_count(self):
        return len(self.backlog)

    def is_backlogged(self):
        return self.backlog != []

    def is_waiting(self):
        return self.status == 'waiting'

    def is_in_DIFS(self):
        return self.status == 'DIFS'

    def is_in_backoff(self):
        return self.status == 'backoff'

    def is_in_transmission(self):
        return self.status == 'transmission'

    def get_next_arrival(self):
        # need lambda in "frames / slot"
        # traffic_rate given in frames / second
        # so divide traffic_rate by number of slots per second
        factor = 10**6/20  # slots/second
        self.next_arrival_in = int((-math.log(1-random.uniform(0, 1))
                                    / (self.traffic_rate/factor)))
        self.total_frames_gen += 1

    def update_traffic(self, slot):
        # need to make sure we never randomly generate 0
        # hence the while loop below
        if self.next_arrival_in > 0:
            self.next_arrival_in -= 1
        # update backlog if timer is now 0
        else:
            self.backlog.append(slot)
            # print(f"updating backlog: {self.backlog}")
            while self.next_arrival_in == 0:
                self.get_next_arrival()

    def reset_DIFS_timer(self):
        self.DIFS_timer = DIFS_length

    def decrement_DIFS_timer(self):
        self.DIFS_timer -= 1

    def decrement_backoff_timer(self):
        self.backoff_timer -= 1

    def decrement_transmission_timer(self):
        self.transmission_timer -= 1

    def increment_frames_transmitted(self):
        self.frames_transmitted += 1

    def get_random_backoff_time(self):
        self.backoff_timer = random.randint(0, self.CW-1)

    def set_status(self, status):
        self.status = status

    def next_CW(self):
        if self.CW < CWmax:
            self.CW = 2*self.CW
        else:
            pass

    def reset_CW(self):
        self.CW = CW0

    def start_transmission_timer(self):
        self.transmission_timer = frame_transmission_time

    def set_occupation_timer_status(self, status):
        self.occupation_timer_status = status  # 'on' or 'off'

    def increment_occupied_slots_count(self):
        self.occupied_slots_count += 1


def generateStations():
    return [station(f"S{i}", random.uniform(MIN_ARRIVAL_RATE, MAX_ARRIVAL_RATE)) for i in range(node_count)]


class simulation:
    def __init__(self, duration):
        # duration is a global parameter measured in frames
        # rate given in frames/sec
        # (converted to frames/slot when getting interarrival times)
        self.duration = duration  # in slots
        self.slot = 0
        self.ACK_timer = 0

        self.channel = channel()
        self.stations = generateStations()
        print(f"generated {len(self.stations)} stations")
        # if self.ratio == 2:
        #     self.stations = [station('A', 2*self.traffic_rate),
        #                      station('C', self.traffic_rate)]

        self.transmitting_stations = []
        self.total_frame_count = []

        for S in self.stations:
            S.get_next_arrival()

        self.collision_counter = 0

    def collision_count(self):
        return self.collision_counter

    def throughputs(self):
        # want to get throughputs in Kbps
        # frame_size is in bits,
        # duration is in slots
        factor = 10**6/20  # slots/second
        return [S.frames_transmitted*(frame_size/1000)
                / float(self.duration/factor) for S in self.stations]

    def delay_lengths(self):
        return [S.delay_list for S in self.stations]

    def average_delays(self):
        delays = []
        for S in self.stations:
            delay_len = len(S.delay_list)
            delay_sum = sum(S.delay_list)
            avg = delay_sum/delay_len if delay_len != 0 else 0
            delays.append(avg or 0)

        return delays

    def export_csv(self):
        with open("report.csv", mode="w") as f:
            headers = ["station #",
                       "packets_transmitted", "collisions", "collision_prob"]
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for i in range(len(self.stations)):
                S = self.stations[i]
                writer.writerow(
                    {
                        "station #": i,
                        "packets_transmitted": S.frames_transmitted,
                        "collisions": S.collision_count,
                        "collision_prob": S.collision_count/S.frames_transmitted if S.frames_transmitted else 1})

    def get_total_frame_count(self):
        return [S.total_frames_gen for S in self.stations]

    def occupied_slots_counts(self):
        return [S.occupied_slots_count for S in self.stations]

    def run(self):
        while self.slot < self.duration:
            # print(self.slot)

            for S in self.stations:
                S.update_traffic(self.slot)
                # print(S.next_arrival_in)
                # S.FAKE_update_traffic(S.name)

            # populate self.backlogged_stations
            self.backlogged_stations = [S for S in self.stations
                                        if S.is_backlogged()]

            # print(f"# of backlogged: {len(self.backlogged_stations)}")

            # populate self.transmitting_stations
            self.transmitting_stations = [S for S in self.stations
                                          if S.is_in_transmission()]

            # set channel to busy if some station is transmitting
            if len(self.transmitting_stations) > 0:
                self.channel.set_status('busy')

            # if no station is backlogged, nothing happens
            # note: you are "backlogged" with frame
            # until you receive an ACK for it
            if self.backlogged_stations == []:
                self.slot += 1
                continue

            # increment occupation timer if it's on
            for S in self.stations:
                if S.occupation_timer_status == 'on':
                    S.increment_occupied_slots_count()

    # past here, some station is backlogged

    # scenario: channel is busy
            if self.channel.status == 'busy':
                # stations not transmitting respond to channel becoming busy
                for S in [S for S in self.backlogged_stations
                          if S not in self.transmitting_stations]:
                    if S.is_waiting():
                        pass
                    elif S.is_in_DIFS():
                        S.reset_DIFS_timer()  # the channel has become busy
                    elif S.is_in_backoff():
                        pass  # freezes backoff timer

                # print(f"# of trans st: {len(self.transmitting_stations)}")
                # now deal with transmitting stations
                if len(self.transmitting_stations) < 2:  # ACK; no collision

                    S = self.transmitting_stations[0]
                    # print(f"transmitting {S.transmission_timer}")

                    if S.transmission_timer > 0:
                        S.decrement_transmission_timer()
                    else:
                        # ACK received!
                        S.increment_frames_transmitted()
                        S.delay_list.append(self.slot-S.backlog[0])
                        # print("appending delay")
                        S.backlog = S.backlog[1:]

                        S.set_occupation_timer_status('off')

                        for T in self.stations:
                            if T.is_backlogged():
                                T.set_status('DIFS')
                                if T.DIFS_timer == 0:
                                    T.reset_DIFS_timer()
                            else:
                                T.set_status('waiting')
                            T.reset_CW()
                        self.channel.set_status('idle')

                else:   # collision imminent or occurring
                    self.collision_counter += 1
                    for s in self.stations:
                        s.reset_CW()
                        if s.is_in_transmission():
                            s.collision_count += 1
                            s.total_frames_dropped += 1

                            s.backlog = s.backlog[1:]  # no retransmission

                        if s.is_backlogged():
                            s.set_status('DIFS')
                            if s.DIFS_timer == 0:
                                s.reset_DIFS_timer()
                        else:
                            s.set_status('waiting')
                            s.set_occupation_timer_status('off')

                    self.channel.set_status('idle')

                    # for S in self.transmitting_stations:
                    #     S.next_CW()
                    #     S.collision_count += 1
                    #     S.set_status('backoff')
                    #     S.set_occupation_timer_status('off')
                    #     S.get_random_backoff_time()
                    #     self.channel.set_status('idle')

                self.slot += 1

        # scenario: channel is idle (and some station is backlogged)
            else:
                for S in self.backlogged_stations:
                    if S.is_waiting():
                        S.set_status('DIFS')
                        S.reset_DIFS_timer()

                    elif S.is_in_DIFS():
                        if S.DIFS_timer > 0:
                            S.decrement_DIFS_timer()
                        else:
                            # DIFS timer has expired
                            # (without interruption due to activity on channel)
                            # begin backoff
                            S.set_status('backoff')
                            if S.backoff_timer == 0:
                                S.get_random_backoff_time()
                    if S.is_in_backoff():
                        if S.backoff_timer > 0:
                            S.decrement_backoff_timer()
                        else:
                            S.set_status('transmission')
                            S.set_occupation_timer_status('on')
                            # self.ACK_timer = ACK_transmission_time + 1
                            # +1 takes care of SIFS
                            S.start_transmission_timer()
                self.slot += 1


class experiment:
    def __init__(self, duration):
        self.duration = duration
        Sim = simulation(self.duration)
        Sim.run()

        throughputs = Sim.throughputs()
        avg_throughput = sum(throughputs) / len(throughputs)

        avg_delays = Sim.average_delays()
        avg_delay = sum(avg_delays) / len(avg_delays)

        print(f"Ran simulation for: {SIM_TIME_SECONDS}")
        print(f"Arrival Rate: {MIN_ARRIVAL_RATE} - {MAX_ARRIVAL_RATE}")
        print("Throughputs | Unit: Kbps")
        print(avg_throughput)
        print()
        print("Average delays | Unit: slots")
        print(avg_delay)
        print()
        print("Collision counts")
        print("Unit: number of collisions")
        print(Sim.collision_count())
        print()

        print(f"Total generated: {Sim.get_total_frame_count()}")

        Sim.export_csv()


cProfile.run('experiment(global_duration)')
