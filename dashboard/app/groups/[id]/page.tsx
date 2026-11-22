"use client";

import { useParams } from "next/navigation";
import { GroupDetails } from "@/components/groups/GroupDetails";
import { Notice } from "@/components/shared/Notice";

export default function GroupDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params?.id);
  if (!Number.isFinite(id)) return <Notice>Invalid group ID.</Notice>;
  return <GroupDetails groupId={id} />;
}
