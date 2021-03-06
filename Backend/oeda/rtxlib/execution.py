from oeda.log import *
import traceback

def _defaultChangeProvider(variables,wf):
    """ by default we just forward the message to the change provider """
    return variables

def experimentFunction(wf, exp):

    if hasattr(wf, "experimentCounter"):
        wf.remaining_time_and_stages['remaining_stages'] = wf.totalExperiments - wf.experimentCounter

    """ executes a given experiment stage """
    start_time = current_milli_time()
    # remove all old data from the queues
    wf.primary_data_provider["instance"].reset()

    # load change event creator or use a default
    if hasattr(wf, "change_event_creator"):
        change_creator = wf.change_event_creator
    else:
        change_creator = _defaultChangeProvider

    # start
    info(">")
    info("> KnobValues     | " + str(exp["knobs"]))
    # create new state
    exp["state"] = wf.state_initializer(dict(), wf)

    # apply changes to system
    try:
        wf.change_provider["instance"].applyChange(change_creator(exp["knobs"], wf))
    except:
        error("apply changes did not work")

    # ignore the first data sets
    to_ignore = exp["ignore_first_n_results"]
    if to_ignore > 0:
        i = 0
        while i < to_ignore:
            new_data = wf.primary_data_provider["instance"].returnData()
            if new_data is not None:
                i += 1
                # NEW - we call back to oeda and give us infos there
                wf.run_oeda_callback({"experiment": exp,
                                      "status": "IGNORING_SAMPLES",
                                      "index": i,
                                      "size": to_ignore,
                                      str("current_knob"): dict(exp["knobs"]),
                                      "remaining_time_and_stages": wf.remaining_time_and_stages})
                process("IgnoreSamples  | ", i, to_ignore)
                # NEW - we check for any interruption flags
                if wf._oeda_stop_request.isSet():
                    raise RuntimeError("Experiment interrupted from OEDA while ignoring data.")
        print("")

    # start collecting data
    sample_size = exp["sample_size"]
    i = 0
    try:
        while i < sample_size:
            # we start with the primary data provider using blocking returnData
            new_data = wf.primary_data_provider["instance"].returnData()
            if new_data is not None:
                try:
                    # print(new_data)
                    # NEW - we call back to oeda and give us infos there
                    wf.run_oeda_callback({"experiment": exp,
                                          "status": "COLLECTING_DATA",
                                          "index": i, "size": sample_size,
                                          str("current_knob"): dict(exp["knobs"]),
                                          "remaining_time_and_stages": wf.remaining_time_and_stages})
                    exp["state"] = wf.primary_data_provider["data_reducer"](exp["state"], new_data, wf)
                except StopIteration as e:
                    raise  # just fwd
                except RuntimeError as e:
                    raise  # just fwd
                except Exception as e:
                    tb = traceback.format_exc()
                    error("Exception:", str(tb))
                    error("Could not reduce data set: " + str(new_data))
                i += 1
                process("CollectSamples | ", i, sample_size)
            # now we use returnDataListNonBlocking on all secondary data providers
            if hasattr(wf, "secondary_data_providers"):
                for cp in wf.secondary_data_providers:
                    new_data = cp["instance"].returnDataListNonBlocking()
                    for nd in new_data:
                        try:
                            exp["state"] = cp["data_reducer"](exp["state"], nd, wf)
                        except StopIteration as e:
                            raise  # just
                        except RuntimeError as e:
                            raise  # just fwd
                        except Exception as e:
                            tb = traceback.format_exc()
                            error("Exception:", str(tb))
                            error("Could not reduce data set: " + str(nd))
        print("")
    except StopIteration as e:
        # this iteration should stop asap
        error("This stage got stopped as requested by the StopIteration exception:" + str(e))
    try:
        result = wf.evaluator(exp["state"], wf)
    except Exception as e:
        tb = traceback.format_exc()
        result = 0
        error("Evaluator failed", str(tb))
    # we store the counter of this experiment in the workflow
    if hasattr(wf, "experimentCounter"):
        wf.experimentCounter += 1
    else:
        wf.experimentCounter = 1


    # print the results
    duration = current_milli_time() - start_time
    wf.remaining_time_and_stages['remaining_stages'] = wf.totalExperiments - wf.experimentCounter
    wf.remaining_time_and_stages['remaining_time'] = str(wf.remaining_time_and_stages['remaining_stages'] * duration / 1000)

    wf.run_oeda_callback({"experiment": exp, "status": "EXPERIMENT_STAGE_DONE",
                          "experiment_counter": wf.experimentCounter, "total_experiments": wf.totalExperiments,
                          "remaining_time_and_stages": wf.remaining_time_and_stages})
    # do not show stats for forever strategy
    if wf.totalExperiments > 0:
        info("> Statistics     | " + str(wf.experimentCounter) + "/" + str(wf.totalExperiments)
             + " took " + str(duration) + "ms" + " - remaining ~" + wf.remaining_time_and_stages['remaining_time'] + "sec")
    info("> FullState      | " + str(exp["state"]))
    info("> ResultValue    | " + str(result))
    # log the result values into a csv file
    # @todo disabled (!) log_results(wf.folder, exp["knobs"].values() + [result])
    # return the result value of the evaluator
    return result
