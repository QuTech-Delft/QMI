class ps4000a:
    PICO_STATUS = {"PICO_OK": 0}
    PICO_STATUS_LOOKUP = {v: k for k, v in PICO_STATUS.items()}
    PICO_COUPLING = {"AC": 0, "DC": 1}
    PICO_INFO = {"PICO_BATCH_AND_SERIAL": 0x1}
    name = "ps4000a"

    def __init__(self):
        pass

    def ps4000aStop(self):
        return 0

    def ps4000aOpenUnit(self, par_serial):
        return 0

    def ps4000aCloseUnit(self):
        return 0

    def ps4000aGetUnitInfo(self, par_string, max_len, par_size, info):
        return 0

    def ps4000aSetChannel(self, channel, enable, coupling, range_sel, offset):
        return 0

    def ps4000aSetSimpleTrigger(self, enable, channel, threshold, edge, val1, val2):
        return 0

    def ps4000aSetTriggerChannelConditions(self, val1, val2):
        return 0

    def ps4000aIsReady(self, par_ready):
        return 0

    def ps4000aSetDataBuffer(self, chan, buf, buf_len, val1, val2):
        return 0

    def ps4000aGetValues(self, start_index, par_num_samples, down_sample_ratio, down_sample_ratio_mode, segment_index,
                         par_overflow):
        return 0
