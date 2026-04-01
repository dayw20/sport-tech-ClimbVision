from rest_framework import serializers
from .models import Job


class JobSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    result_image_url = serializers.SerializerMethodField()
    frame_image_url = serializers.SerializerMethodField()
    reference_frame_image_url = serializers.SerializerMethodField()
    reference_rectified_image_url = serializers.SerializerMethodField()

    hold_overlay_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "status",
            "message",
            "created_at",
            "updated_at",
            "input_mode",

            # basic urls
            "video_url",
            "result_image_url",
            "frame_image_url",

            # Stage 0: reference plane
            "reference_frame_time",
            "reference_quad",
            "reference_canvas_width",
            "reference_canvas_height",
            "calibration_status",
            "reference_frame_image_url",
            "reference_rectified_image_url",

            # Stage 1/2 intermediate artifacts
            "hold_overlay_image_url",
            "holds_json",
            "projected_pose_json",
            "projected_holds_json",
            "combination_json",
        ]

    def _build_url(self, request, field_file):
        if not field_file:
            return None
        url = field_file.url
        return request.build_absolute_uri(url) if request else url

    def get_video_url(self, obj: Job):
        return self._build_url(self.context.get("request"), obj.video_file)

    def get_result_image_url(self, obj: Job):
        return self._build_url(self.context.get("request"), obj.result_image)

    def get_frame_image_url(self, obj: Job):
        return self._build_url(self.context.get("request"), getattr(obj, "frame_image", None))

    def get_reference_frame_image_url(self, obj: Job):
        return self._build_url(self.context.get("request"), getattr(obj, "reference_frame_image", None))

    def get_reference_rectified_image_url(self, obj: Job):
        return self._build_url(self.context.get("request"), getattr(obj, "reference_rectified_image", None))

    def get_hold_overlay_image_url(self, obj: Job):
        return self._build_url(self.context.get("request"), getattr(obj, "hold_overlay_image", None))