from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import datetime
from controller.views import compose_reply

from controller.models import Submission,PeerGrader,MLGrader,InstructorGrader,SelfAssessmentGrader

@csrf_exempt
@login_required
@statsd.timed('xqueue.ext_interface.put_result.time')
def submit(request):
    '''
    Xqueue pull script posts objects here.
    '''
    if request.method != 'POST':
        return HttpResponse(compose_reply(False, "'submit' must use HTTP POST"))
    else:
        reply_is_valid, header, body = _is_valid_reply(request.POST)

        if not reply_is_valid:
            log.error("Invalid xqueue object added: request_ip: {0} request.POST: {1}".format(
                get_request_ip(request),
                request.POST,
            ))
            return HttpResponse(compose_reply(False, 'Incorrect format'))
        else:
            try:
                prompt=_value_or_default(body['prompt'],"")
                student_id=_value_or_default(body['student_info']['anonymous_student_id'])
                location=_value_or_default(body['grader_payload']['location'])
                problem_id=_value_or_default(body['grader_payload']['problem_id'],location)
                grader_settings=_value_or_default(body['grader_payload']['grader'],"")
                student_response=_value_or_default(body['student_response'])
                xqueue_submission_id=_value_or_default(header['submission_id'])
                xqueue_submission_key=_value_or_default(header['submission_key'])
                state_code="W"

                submission_time_string=_value_or_default(body['student_info']['submission_time'])
                student_submission_time=datetime.strptime(submission_time_string,"%Y%m%d%H%M%S")

                sub, created = Submission.objects.get_or_create(
                    prompt=prompt,
                    student_id=student_id,
                    problem_id=problem_id,
                    state=state_code,
                    student_response=student_response,
                    student_submission_time=student_submission_time,
                    xqueue_submission_id=xqueue_submission_id,
                    xqueue_submission_key=xqueue_submission_key,
                    location=location,
                )

                log.debug(sub)
                log.debug("Created successfully!")

                sub.save()

            except Exception as err:
                log.error("Error creating submission and adding to database: sender: {0}, submission_id: {1}, submission_key: {2}".format(
                    get_request_ip(request),
                    xqueue_submission_id,
                    xqueue_submission_key,
                ))
                return HttpResponse(compose_reply(False,'Submission does not exist'))

            #Handle submission after writing it to db

            return HttpResponse(compose_reply(success=True, content=''))

def _value_or_default(value,default=None):
    if value is not None:
        return value
    elif default is not None:
        return default
    else:
        error="Needed value not passed by xqueue."
        #TODO: Fix in future to fail in a more robust way
        raise Exception(error)

def _is_valid_reply(external_reply):
    '''
    Check if external reply is in the right format
        1) Presence of 'xqueue_header' and 'xqueue_body'
        2) Presence of specific metadata in 'xqueue_header'
            ['submission_id', 'submission_key']

    Returns:
        is_valid:       Flag indicating success (Boolean)
        submission_id:  Graded submission's database ID in Xqueue (int)
        submission_key: Secret key to match against Xqueue database (string)
        score_msg:      Grading result from external grader (string)
    '''
    fail = (False,-1,'','')
    try:
        header    = external_reply['xqueue_header']
        body = external_reply['xqueue_body']
    except KeyError:
        return fail

    if not isinstance(header,dict) or not isinstance(body,dict):
        return fail

    for tag in ['submission_id', 'submission_key']:
        if not header.has_key(tag):
            return fail

    for tag in ['grader_payload', 'student_response', 'student_info']
        if not body.has_key(tag):
            return fail

    return True,header,body

