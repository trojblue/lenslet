#!/bin/bash

"$HOME"/s5cmd sync \
  "s3://dataset-ingested/datagen_workspace/05_dit02_hires/output/distill_dit_hires_user-prompt_bestof16-m1-aes12/*" \
  "./data/distill_dit_hires_user-prompt_bestof16-m1-aes12/"

"$HOME"/s5cmd sync \
  "s3://dataset-ingested/datagen_workspace/05_dit02_hires/output/distill_dit_hires_danbooru-10k-m1-aes12-1x/*" \
  "./data/distill_dit_hires_danbooru-10k-m1-aes12-1x/"

"$HOME"/s5cmd sync \
  "s3://dataset-ingested/datagen_workspace/05_dit02_hires/output/distill_dit_hires_vis_user_prompts-m1-aes12-3x/*" \
  "./data/distill_dit_hires_vis_user_prompts-m1-aes12-3x/"

python -m src.lenscat_backend.workers.run_worker