from rest_framework.decorators import api_view, parser_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from pathlib import Path
from django.core.files.base import ContentFile

from .models import Job
from .serializers import JobSerializer
from .extract import extract_frame_at_time
from .calibration import auto_calibrate_reference_frame, extract_reference_frame_for_job

@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})

@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def create_job(request):
    video = request.FILES.get("video")
    if not video:
        return Response({"error": "missing 'video' file"}, status=status.HTTP_400_BAD_REQUEST)

    job = Job.objects.create(status=Job.Status.QUEUED, message="queued")
    job.video_file.save(f"{job.id}.mp4", video, save=True)

    # 立即抽第一张 frame（占位用），并写入 frame_image + result_image
    try:
        video_path = Path(job.video_file.path)
        t_preview = 0.5  # 避开 t=0 可能黑帧
        tmp_out = Path("/tmp") / f"{job.id}_preview.jpg"

        extract_frame_at_time(video_path, tmp_out, t_seconds=t_preview)

        with open(tmp_out, "rb") as f:
            b = f.read()

        # 1) 给“模型 input debug”用
        job.frame_image.save(f"{job.id}_frame.jpg", ContentFile(b), save=False)

        # 2) 给“前端结果图占位”用（先用第一帧顶着）
        job.result_image.save(f"{job.id}_result.jpg", ContentFile(b), save=False)

        job.input_mode = Job.InputMode.FRAME  # 可选：标记一下
        job.save(update_fields=["frame_image", "result_image", "input_mode", "updated_at"])
    except Exception as e:
        # 抽帧失败不影响创建任务
        job.message = f"queued (preview extract failed: {e})"
        job.save(update_fields=["message", "updated_at"])


    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_201_CREATED)

@api_view(["GET"])
def get_job(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data)

@api_view(["GET"])
def get_frame(request, job_id):
    """
    GET /api/jobs/{job_id}/frame/?t=0
    Extracts a frame from the uploaded video and stores it in job.frame_image.
    Returns the job JSON including frame_image_url.
    """
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    if not job.video_file:
        return Response({"error": "job has no video_file"}, status=status.HTTP_400_BAD_REQUEST)

    # parse t seconds
    t_str = request.query_params.get("t", "0")
    try:
        t = float(t_str)
        if t < 0:
            t = 0.0
    except ValueError:
        t = 0.0

    # 如果已存在且用户没换时间点，可以直接返回（简单起见先总是重新抽也行）
    # 这里先做“总是重新抽”，确保 t 参数生效：
    video_path = Path(job.video_file.path)
    tmp_out = Path("/tmp") / f"{job_id}_t{t}.jpg"

    try:
        extract_frame_at_time(video_path, tmp_out, t_seconds=t)
    except Exception as e:
        return Response({"error": f"extract frame failed: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    with open(tmp_out, "rb") as f:
        job.frame_image.save(f"{job_id}_frame.jpg", ContentFile(f.read()), save=True)

    # 标记 input_mode（可选）
    job.input_mode = Job.InputMode.FRAME
    job.save(update_fields=["input_mode", "updated_at"])

    data = JobSerializer(job, context={"request": request}).data
    return Response(data)

@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_result(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    image = request.FILES.get("image")
    if not image:
        return Response({"error": "missing 'image' file"}, status=status.HTTP_400_BAD_REQUEST)

    # 保存结果图
    job.result_image.save(f"{job.id}_result.jpg", image, save=False)
    job.status = Job.Status.DONE
    job.message = "result uploaded"
    job.save(update_fields=["result_image", "status", "message", "updated_at"])

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)

@api_view(["POST"])
def generate_reference_frame(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    if not job.video_file:
        return Response({"error": "job has no video_file"}, status=status.HTTP_400_BAD_REQUEST)

    t_str = request.data.get("t", 0.5)
    try:
        t = float(t_str)
        if t < 0:
            t = 0.0
    except (TypeError, ValueError):
        t = 0.5

    try:
        extract_reference_frame_for_job(job, t_seconds=t)
        auto_applied = auto_calibrate_reference_frame(job)
        if auto_applied:
            job.message = "model calibration ready"
            job.save(update_fields=["message", "updated_at"])
        else:
            job.calibration_status = Job.CalibrationStatus.NOT_SET
            job.message = "reference frame ready - review model suggestion or select 4 points manually"
            job.save(update_fields=["calibration_status", "message", "updated_at"])
    except Exception as e:
        job.calibration_status = Job.CalibrationStatus.ERROR
        job.message = f"reference frame generation failed: {e}"
        job.save(update_fields=["calibration_status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)

@api_view(["POST"])
def set_reference_quad(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    quad = request.data.get("quad")
    if not quad:
        return Response({"error": "missing 'quad'"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from .calibration import save_reference_calibration
        save_reference_calibration(job, quad)
        job.message = "reference plane ready"
        job.save(update_fields=["message", "updated_at"])
    except Exception as e:
        job.calibration_status = Job.CalibrationStatus.ERROR
        job.message = f"reference calibration failed: {e}"
        job.save(update_fields=["calibration_status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)

@api_view(["POST"])
def run_pose_debug(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    if not job.video_file:
        return Response({"error": "job has no video_file"}, status=status.HTTP_400_BAD_REQUEST)

    if job.calibration_status != Job.CalibrationStatus.READY:
        return Response(
            {"error": "reference plane is not ready yet"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    n_frames = request.data.get("n_frames", 6)
    pose_model = request.data.get("pose_model", "lite")

    try:
        n_frames = int(n_frames)
        if n_frames <= 0:
            n_frames = 6
    except (TypeError, ValueError):
        n_frames = 6

    try:
        from .pose_debug import build_pose_debug_composite_for_job

        job.status = Job.Status.PROCESSING
        job.message = "running pose debug..."
        job.save(update_fields=["status", "message", "updated_at"])

        build_pose_debug_composite_for_job(
            job,
            n_frames=n_frames,
            pose_model=pose_model,
        )
    except Exception as e:
        job.status = Job.Status.ERROR
        job.message = f"pose debug failed: {e}"
        job.save(update_fields=["status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)

@api_view(["POST"])
def run_projected_pose_summary(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    if job.calibration_status != Job.CalibrationStatus.READY:
        return Response(
            {"error": "reference plane is not ready yet"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    n_frames = request.data.get("n_frames", 6)
    pose_model = request.data.get("pose_model", "lite")

    try:
        n_frames = int(n_frames)
        if n_frames <= 0:
            n_frames = 6
    except (TypeError, ValueError):
        n_frames = 6

    try:
        from .pose_summary import build_projected_pose_summary_for_job

        job.status = Job.Status.PROCESSING
        job.message = "running projected pose summary..."
        job.save(update_fields=["status", "message", "updated_at"])

        build_projected_pose_summary_for_job(
            job,
            n_frames=n_frames,
            pose_model=pose_model,
        )
    except Exception as e:
        job.status = Job.Status.ERROR
        job.message = f"projected pose summary failed: {e}"
        job.save(update_fields=["status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)

@api_view(["POST"])
def run_pose_trajectory(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    if job.calibration_status != Job.CalibrationStatus.READY:
        return Response(
            {"error": "reference plane is not ready yet"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    pose_model = request.data.get("pose_model", "lite")

    try:
        from .pose_summary import build_pose_trajectory_for_job

        job.status = Job.Status.PROCESSING
        job.message = "running pose trajectory..."
        job.save(update_fields=["status", "message", "updated_at"])

        build_pose_trajectory_for_job(job, pose_model=pose_model)
    except Exception as e:
        job.status = Job.Status.ERROR
        job.message = f"pose trajectory failed: {e}"
        job.save(update_fields=["status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
def run_combination(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    radius_px = float(request.data.get("radius_px", 0.0))
    min_consecutive_frames = int(request.data.get("min_consecutive_frames", 1))

    try:
        from .combination import build_combination_for_job

        job.status = Job.Status.PROCESSING
        job.message = "running combination..."
        job.save(update_fields=["status", "message", "updated_at"])

        build_combination_for_job(job, radius_px=radius_px, min_consecutive_frames=min_consecutive_frames)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        job.status = Job.Status.ERROR
        job.message = f"combination failed: {e}"
        job.save(update_fields=["status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
def run_projected_hold_summary(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

    if job.calibration_status != Job.CalibrationStatus.READY:
        return Response(
            {"error": "reference plane is not ready yet"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from .hold_summary import build_projected_hold_summary_for_job

        job.status = Job.Status.PROCESSING
        job.message = "running projected hold summary..."
        job.save(update_fields=["status", "message", "updated_at"])

        build_projected_hold_summary_for_job(job)

    except Exception as e:
        job.status = Job.Status.ERROR
        job.message = f"projected hold summary failed: {e}"
        job.save(update_fields=["status", "message", "updated_at"])
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    data = JobSerializer(job, context={"request": request}).data
    return Response(data, status=status.HTTP_200_OK)
