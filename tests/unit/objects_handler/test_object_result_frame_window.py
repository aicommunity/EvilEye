from evileye.objects_handler.object_result import ObjectResult, ObjectResultHistory, ObjectResultList


def test_find_objects_near_frame_id_matches_by_current_frame():
    obj = ObjectResult()
    obj.frame_id = 101
    result = ObjectResultList()
    result.objects.append(obj)

    near = result.find_objects_near_frame_id(100, max_delta=1, use_history=False)
    assert len(near) == 1


def test_find_objects_near_frame_id_matches_by_history():
    obj = ObjectResult()
    obj.frame_id = 110
    hist = ObjectResultHistory()
    hist.frame_id = 100
    obj.history.append(hist)

    result = ObjectResultList()
    result.objects.append(obj)

    near = result.find_objects_near_frame_id(101, max_delta=1, use_history=True)
    assert len(near) == 1
