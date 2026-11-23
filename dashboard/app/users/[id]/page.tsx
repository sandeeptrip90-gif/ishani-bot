"use client";

import { useParams } from "next/navigation";
import { UserChatHistory } from "@/components/chat/UserChatHistory";
import { Notice } from "@/components/shared/Notice";

export default function UserDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params?.id);
  if (!Number.isFinite(id) || id <= 0) return <Notice>Invalid user ID.</Notice>;
  return <UserChatHistory userId={id} />;
}
