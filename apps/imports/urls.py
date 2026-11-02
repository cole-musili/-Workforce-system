
from django.urls import path

from . import views


app_name = "imports"


urlpatterns = [
    # Upload and import history
    path(
        "",
        views.import_upload,
        name="upload",
    ),

    path(
        "history/",
        views.import_history,
        name="history",
    ),

    # Worksheet selection
    path(
        "<int:batch_id>/worksheets/",
        views.select_worksheets,
        name="select_worksheets",
    ),

    # Import review
    path(
        "<int:batch_id>/review/",
        views.review_batch,
        name="review",
    ),

    # Individual row management
    path(
        "<int:batch_id>/row/<int:row_id>/edit/",
        views.edit_import_row,
        name="edit_row",
    ),

    path(
        "<int:batch_id>/row/<int:row_id>/action/",
        views.update_row_action,
        name="row_action",
    ),

    # Bulk selection and correction
    path(
        "<int:batch_id>/selection/",
        views.update_selection,
        name="update_selection",
    ),

    path(
        "<int:batch_id>/bulk-correct/",
        views.bulk_correct,
        name="bulk_correct",
    ),

    # Custom field management
    path(
        "<int:batch_id>/fields/",
        views.manage_custom_fields,
        name="custom_fields",
    ),

    # Import confirmation and processing
    path(
        "<int:batch_id>/confirm/",
        views.confirm_import,
        name="confirm",
    ),
]
