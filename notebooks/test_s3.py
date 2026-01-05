

import pandas as pd
import lenslet


if __name__ == "__main__":
    import unibox as ub

    imgs = ub.ls("s3://bucket-public-access-uw2/labelling2/export_aiimg_goods_batch1/zeka-old-5star/", ub.IMG_FILES)
    # Example: DataFrame with mixed local and S3 images
    df = pd.DataFrame({
        'image_path': imgs,
        # 'label': ['cat', 'dog', 'cat']
    })

    # Launch with multiple datasets
    datasets = {
        "all_images": df['image_path'].tolist(),
        # "cats_only": df[df['label'] == 'cat']['image_path'].tolist(),
    }

    lenslet.launch(datasets, blocking=True, port=7071, verbose=True)
