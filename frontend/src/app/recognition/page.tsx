import type { Metadata } from "next";

import { FoundationPanel, PageHeader } from "@/components/page-layout";

export const metadata: Metadata = {
  title: "Recognition",
};

export default function RecognitionPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Still-image workflow"
        title="Recognition"
        description="The route and accessible layout are ready. Image selection, submission, and result presentation belong to Day 13."
      />
      <FoundationPanel
        title="Recognition workspace"
        description="No image is selected. This foundation does not upload files, run models, or make entry decisions."
      />
    </div>
  );
}
