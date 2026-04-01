from django.urls import path
from .views import (
    health,
    create_job,
    get_job,
    get_frame,
    upload_result,
    generate_reference_frame,
    set_reference_quad,
    run_pose_debug,
    run_projected_pose_summary,
    run_pose_trajectory,
    run_projected_hold_summary,
    run_combination,
)

urlpatterns = [
    path("health/", health),
    path("jobs/", create_job),
    path("jobs/<uuid:job_id>/", get_job),
    path("jobs/<uuid:job_id>/frame/", get_frame),
    path("jobs/<uuid:job_id>/upload-result/", upload_result),

    # Stage 0
    path("jobs/<uuid:job_id>/reference-frame/", generate_reference_frame),
    path("jobs/<uuid:job_id>/reference-quad/", set_reference_quad),

    path("jobs/<uuid:job_id>/pose-debug/", run_pose_debug),
    path("jobs/<uuid:job_id>/projected-pose-summary/", run_projected_pose_summary),
    path("jobs/<uuid:job_id>/pose-trajectory/", run_pose_trajectory),
    path("jobs/<uuid:job_id>/projected-holds/", run_projected_hold_summary),
    path("jobs/<uuid:job_id>/combine/", run_combination),
]