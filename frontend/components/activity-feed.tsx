"use client";

/**
 * ActivityFeed Component
 *
 * Displays recent agent activity including:
 * - Reddit comments/posts
 * - Belief updates
 * - Moderation actions
 * - Timestamp and context for each activity
 */

export default function ActivityFeed() {
  return (
    <div className="w-full p-4 border rounded-lg">
      <h2 className="text-xl font-semibold mb-4">Activity Feed</h2>
      <div className="space-y-3">
        <div className="p-3 bg-gray-50 rounded">
          <p className="text-sm text-gray-500">No recent activity</p>
        </div>
      </div>
    </div>
  );
}
