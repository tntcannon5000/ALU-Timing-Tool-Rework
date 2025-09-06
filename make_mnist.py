# --- SETUP CELL: RUN THIS ONCE TO CREATE THE MODEL ---
import tensorflow as tf
import numpy as np
import os

def create_and_train_mnist_model():
    """
    Defines, trains, and saves a simple CNN for MNIST digit recognition.
    This is very fast and only needs to be run once.
    """
    print("Loading MNIST dataset...")
    (x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

    # Preprocess the data: normalize and add a channel dimension
    x_train = x_train.astype("float32") / 255.0
    x_test = x_test.astype("float32") / 255.0
    x_train = np.expand_dims(x_train, -1)
    x_test = np.expand_dims(x_test, -1)

    # Define the simple CNN model
    model = tf.keras.Sequential([
        tf.keras.Input(shape=(28, 28, 1)),
        tf.keras.layers.Conv2D(32, kernel_size=(3, 3), activation="relu"),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
        tf.keras.layers.Conv2D(64, kernel_size=(3, 3), activation="relu"),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dropout(0.5),
        tf.keras.layers.Dense(10, activation="softmax"), # 10 classes for digits 0-9
    ])

    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])

    print("Training the model (this will be quick)...")
    model.fit(x_train, y_train, batch_size=128, epochs=5, validation_split=0.1)

    print("Evaluating final model...")
    score = model.evaluate(x_test, y_test, verbose=0)
    print(f"Test loss: {score[0]}")
    print(f"Test accuracy: {score[1]}")

    model_path = "mnist_model.h5"
    model.save(model_path)
    print(f"Model saved to {model_path}")

# Check if model exists, if not, create it.
if not os.path.exists("mnist_model.h5"):
    create_and_train_mnist_model()

# Load the pretrained model for use in the main loop
mnist_classifier = tf.keras.models.load_model("mnist_model.h5")
print("MNIST model loaded successfully.")