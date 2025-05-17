# Make sure to install the library: pip install google-cloud-videointelligence
# And set up your GOOGLE_APPLICATION_CREDENTIALS environment variable.

from google.cloud import videointelligence_v1p3beta1 as videointelligence

def analyze_video_activity(gcs_uri: str) -> str:
    """
    Analyzes a video stored in Google Cloud Storage to detect labels (activities, objects)
    and persons. Returns a descriptive string of the findings.

    Args:
        gcs_uri: The Google Cloud Storage URI of the video.
                 (e.g., "gs://your-bucket/your-video.mp4")

    Returns:
        A string summarizing the detected activities and persons in the video.
    """
    print(f"Analyzing video: {gcs_uri}")

    video_client = videointelligence.VideoIntelligenceServiceClient()

    features = [
        videointelligence.Feature.LABEL_DETECTION,
        videointelligence.Feature.PERSON_DETECTION,
        # You can also add videointelligence.Feature.OBJECT_TRACKING for more detail
    ]

    # Configuration for person detection (optional, but can be useful)
    person_detection_config = videointelligence.PersonDetectionConfig(
        include_bounding_boxes=True,
        include_attributes=False,  # Set to True if you need attributes like pose
        include_pose_landmarks=False, # Set to True for pose landmarks
    )
    video_context = videointelligence.VideoContext(
        person_detection_config=person_detection_config
    )

    try:
        operation = video_client.annotate_video(
            request={
                "input_uri": gcs_uri,
                "features": features,
                "video_context": video_context,
            }
        )

        print("\nProcessing video for annotations...")
        result = operation.result(timeout=300) # Adjust timeout as needed for longer videos
        print("\nFinished processing.")

        summary_parts = []

        # --- Process Label Detection Results ---
        # Labels can describe scenes, objects, and actions
        label_annotations = result.annotation_results[0].segment_label_annotations
        if label_annotations:
            summary_parts.append("Detected activities/objects/scenes:")
            # Sort labels by average confidence or filter by entity description
            # For simplicity, we'll list a few prominent ones.
            unique_labels = {}
            for label in label_annotations:
                description = label.entity.description
                for segment in label.segments:
                    confidence = segment.confidence
                    if description not in unique_labels or unique_labels[description] < confidence:
                        unique_labels[description] = confidence

            # Sort by confidence (descending) and take top N
            sorted_labels = sorted(unique_labels.items(), key=lambda item: item[1], reverse=True)
            for desc, conf in sorted_labels[:5]: # Display top 5 labels
                 summary_parts.append(f"- {desc} (confidence: {conf:.2f})")
        else:
            summary_parts.append("No significant labels detected.")

        # --- Process Person Detection Results ---
        person_annotations = result.annotation_results[0].person_detection_annotations
        if person_annotations:
            summary_parts.append("\nPerson detection details:")
            num_detected_persons = len(person_annotations)
            summary_parts.append(f"- Detected {num_detected_persons} person track(s).")

            for i, person_annotation in enumerate(person_annotations):
                summary_parts.append(f"  Person Track {i+1}:")
                # Each track contains segments where the person is visible
                for track in person_annotation.tracks:
                    start_time = track.segment.start_time_offset.total_seconds()
                    end_time = track.segment.end_time_offset.total_seconds()
                    summary_parts.append(f"    - Visible from {start_time:.2f}s to {end_time:.2f}s")
                    # You can also access track.timestamped_objects for frame-by-frame bounding boxes
                    # For a "short description", we'll keep it high-level.
        else:
            summary_parts.append("\nNo persons detected in the video.")

        return "\n".join(summary_parts)

    except Exception as e:
        return f"An error occurred: {e}"

# --- Example Usage ---
if __name__ == "__main__":
    # **IMPORTANT**: Replace with the GCS URI of your video file.
    # The video must be uploaded to a Google Cloud Storage bucket.
    # For example: video_gcs_uri = "gs://your-gcs-bucket-name/your-video-file.mp4"
    video_gcs_uri = "gs://cloud-samples-data/video/cat.mp4" # A sample video provided by Google
    # video_gcs_uri = "gs://cloud-samples-data/video/googlework_short.mp4" # Another sample

    if video_gcs_uri.startswith("gs://your-gcs-bucket-name"):
        print("Please replace 'gs://your-gcs-bucket-name/your-video-file.mp4' with an actual GCS URI.")
    else:
        description = analyze_video_activity(video_gcs_uri)
        print("\n--- Video Analysis Summary ---")
        print(description)

        # For a very "short description" of what a user might be doing,
        # you might primarily focus on the top few labels that are actions.
        # For example:
        # prominent_actions = [label for label in sorted_labels[:3] if label[0] in ["talking", "typing", "walking", "running", "dancing", "playing"]] # etc.
        # if prominent_actions:
        #     print(f"\nPotential user actions: {', '.join([a[0] for a in prominent_actions])}")
        # if any("person" in desc.lower() for desc in unique_labels): # A bit simplistic
        #     print("A person appears to be present and active in the video.")