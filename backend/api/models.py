from django.db import models
import uuid

class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        ERROR = "error", "Error"

    class InputMode(models.TextChoices):
        VIDEO = "video", "Video"
        FRAME = "frame", "Frame"

    class CalibrationStatus(models.TextChoices):
        NOT_SET = "not_set", "Not Set"
        READY = "ready", "Ready"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)

    input_mode = models.CharField(max_length=16, choices=InputMode.choices, default=InputMode.VIDEO)

    video_file = models.FileField(upload_to="videos/", null=True, blank=True)
    frame_image = models.ImageField(upload_to="frames/", null=True, blank=True)   
    result_image = models.ImageField(upload_to="results/", null=True, blank=True)

    # --- Stage 0: reference plane ---
    reference_frame_image = models.ImageField(upload_to="reference_frames/", null=True, blank=True)
    reference_rectified_image = models.ImageField(upload_to="reference_rectified/", null=True, blank=True)
    reference_frame_time = models.FloatField(default=0.5)
    reference_quad = models.JSONField(null=True, blank=True)   # [[x,y],[x,y],[x,y],[x,y]]
    reference_canvas_width = models.IntegerField(null=True, blank=True)
    reference_canvas_height = models.IntegerField(null=True, blank=True)
    calibration_status = models.CharField(
        max_length=16,
        choices=CalibrationStatus.choices,
        default=CalibrationStatus.NOT_SET,
    )

    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

        # --- Stage 1/2 intermediate artifacts ---
    hold_annotated_image = models.ImageField(upload_to="hold_annotated/", null=True, blank=True)
    hold_overlay_image = models.ImageField(upload_to="hold_overlays/", null=True, blank=True)
    pose_result_image = models.ImageField(upload_to="pose_results/", null=True, blank=True)
    clean_summary_image = models.ImageField(upload_to="clean_summaries/", null=True, blank=True)

    holds_json = models.JSONField(null=True, blank=True)
    projected_pose_json = models.JSONField(null=True, blank=True)
    projected_holds_json = models.JSONField(null=True, blank=True)
    combination_json = models.JSONField(null=True, blank=True)


    def __str__(self):
        return f"{self.id} ({self.status})"
