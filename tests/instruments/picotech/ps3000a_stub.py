class ps3000a:
    PICO_STATUS = {"PICO_OK": 0}
    PICO_STATUS_LOOKUP = {v: k for k, v in PICO_STATUS.items()}
    PICO_COUPLING = {"AC": 0, "DC": 1}
    PICO_INFO = {"PICO_BATCH_AND_SERIAL": 0x1}
    name = "ps3000a"

    def __init__(self):
        pass

    def ps3000aStop(self):
        return 0

    def ps3000aOpenUnit(self, par_serial):
        return 0

    def ps3000aCloseUnit(self):
        return 0

    def ps3000aGetUnitInfo(self, par_string, max_len, par_size, info):
        return 0

    def ps3000aSetChannel(self, channel, enable, coupling, range_sel, offset):
        return 0

    def ps3000aSetSimpleTrigger(self, enable, channel, threshold, edge, val1, val2):
        return 0

    def ps3000aSetTriggerChannelConditions(self, val1, val2):
        return 0

    def ps3000aIsReady(self, par_ready):
        return 0

    def ps3000aSetDataBuffer(self, chan, buf, buf_len, val1, val2):
        return 0

    def ps3000aGetValues(self, start_index, par_num_samples, down_sample_ratio, down_sample_ratio_mode, segment_index,
                         par_overflow):
        return 0
