import type { Metadata } from "next";

import { PageHeader } from "@/components/page-layout";
import { RecognitionWorkspace } from "@/components/recognition-workspace";

export const metadata: Metadata = {
  title: "Recognition",
};

export default function RecognitionPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Still-image workflow"
        title="Recognition"
        description="Analyze one vehicle image to receive an explainable plate authorization result. This tool supports security review and does not operate a physical gate."
      />
      <RecognitionWorkspace />
    </div>
  );
}
