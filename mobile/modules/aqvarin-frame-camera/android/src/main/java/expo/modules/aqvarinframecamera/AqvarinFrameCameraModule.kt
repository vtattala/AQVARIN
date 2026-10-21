package expo.modules.aqvarinframecamera

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.util.Base64
import android.util.Size
import android.util.Log
import android.view.Surface
import android.view.ViewGroup
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.Promise
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference

class AqvarinFrameCameraModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("AqvarinFrameCamera")
    View(FrameCameraView::class) {
      Events("onReady", "onError")
      Prop("facing") { view: FrameCameraView, facing: String -> view.setFacing(facing) }
      AsyncFunction("captureFrame") { view: FrameCameraView, promise: Promise -> view.requestFrame(promise) }
    }
  }
}

/** Continuous camera preview, converting only the next requested frame.
 * No photos, audio, disk writes, background capture, or accumulating frame queue.
 */
class FrameCameraView(context: Context, private val moduleContext: AppContext) : ExpoView(context, moduleContext) {
  override val shouldUseAndroidLayout = true
  private val onReady by EventDispatcher<Unit>()
  private val onError by EventDispatcher<Map<String, String>>()
  private val previewView = PreviewView(context).apply {
    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
    scaleType = PreviewView.ScaleType.FIT_CENTER
  }
  private val pending = AtomicReference<Promise?>(null)
  private var executor = Executors.newSingleThreadExecutor()
  private var provider: ProcessCameraProvider? = null
  private var preview: Preview? = null
  private var analysis: ImageAnalysis? = null
  private var lens = CameraSelector.LENS_FACING_BACK
  @Volatile private var detached = true
  @Volatile private var ready = false
  private var binding = 0

  init {
    keepScreenOn = true
    addView(previewView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
  }

  fun setFacing(facing: String) {
    val next = if (facing == "front") CameraSelector.LENS_FACING_FRONT else CameraSelector.LENS_FACING_BACK
    if (next != lens) { lens = next; if (!detached) bindCamera() }
  }

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    detached = false
    keepScreenOn = true
    if (executor.isShutdown) executor = Executors.newSingleThreadExecutor()
    bindCamera()
  }

  override fun onLayout(changed: Boolean, left: Int, top: Int, right: Int, bottom: Int) {
    super.onLayout(changed,left,top,right,bottom)
    previewView.layout(0,0,right-left,bottom-top)
    val rotation = display?.rotation ?: Surface.ROTATION_0
    analysis?.targetRotation = rotation
    preview?.targetRotation = rotation
  }

  override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
    measureChild(previewView,widthMeasureSpec,heightMeasureSpec)
    setMeasuredDimension(ViewGroup.resolveSize(previewView.measuredWidth,widthMeasureSpec),
      ViewGroup.resolveSize(previewView.measuredHeight,heightMeasureSpec))
  }

  private fun bindCamera() {
    if (ContextCompat.checkSelfPermission(context,Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
      onError(mapOf("message" to "Camera permission is required.")); return
    }
    val owner = moduleContext.currentActivity as? LifecycleOwner
    if (owner == null) { onError(mapOf("message" to "Camera activity is unavailable.")); return }
    val token = ++binding
    val future = ProcessCameraProvider.getInstance(context)
    future.addListener({
      if (detached || binding != token) return@addListener
      try {
        val cameraProvider = future.get()
        analysis?.let { cameraProvider.unbind(it) }
        preview?.let { cameraProvider.unbind(it) }
        val rotation = display?.rotation ?: Surface.ROTATION_0
        val resolution = ResolutionSelector.Builder()
          .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
          .setResolutionStrategy(ResolutionStrategy(Size(1280,720),ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER))
          .build()
        val feed = Preview.Builder().setResolutionSelector(resolution).setTargetRotation(rotation).build()
        feed.setSurfaceProvider(previewView.surfaceProvider)
        val frames = ImageAnalysis.Builder()
          .setResolutionSelector(resolution)
          .setTargetRotation(rotation)
          .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
          .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
          .build()
        ready = false
        frames.setAnalyzer(executor) { image -> analyze(image) }
        provider = cameraProvider; preview = feed; analysis = frames
        cameraProvider.bindToLifecycle(owner,CameraSelector.Builder().requireLensFacing(lens).build(),feed,frames)
      } catch (error: Exception) { onError(mapOf("message" to (error.message ?: "Camera could not open."))) }
    },ContextCompat.getMainExecutor(context))
  }

  fun requestFrame(promise: Promise) {
    if (detached || !ready) { promise.reject("E_CAMERA_NOT_READY","Camera is not producing frames.",null); return }
    if (!pending.compareAndSet(null,promise)) { promise.reject("E_CAMERA_BUSY","A frame is already being captured.",null); return }
    postDelayed({
      if (pending.compareAndSet(promise,null)) promise.reject("E_CAMERA_TIMEOUT","Camera stopped producing frames.",null)
    },5000)
  }

  private fun analyze(image: ImageProxy) {
    var original: Bitmap? = null
    var oriented: Bitmap? = null
    var request: Promise? = null
    try {
      if (detached) return
      if (!ready) {
        ready = true
        Log.i("AqvarinCamera","Continuous frames ready: ${image.width}x${image.height}, rotation ${image.imageInfo.rotationDegrees}")
        post { if (!detached) onReady(Unit) }
      }
      val consumer = pending.getAndSet(null) ?: return
      request = consumer
      val base = image.toBitmap()
      original = base
      val matrix = Matrix().apply {
        postRotate(image.imageInfo.rotationDegrees.toFloat())
        val scale = minOf(1f,1280f/maxOf(base.width,base.height))
        postScale(scale,scale)
      }
      val encoded = Bitmap.createBitmap(base,0,0,base.width,base.height,matrix,true)
      oriented = encoded
      val bytes = ByteArrayOutputStream()
      if (!encoded.compress(Bitmap.CompressFormat.JPEG,90,bytes)) throw IllegalStateException("Could not encode frame.")
      consumer.resolve(mapOf("base64" to Base64.encodeToString(bytes.toByteArray(),Base64.NO_WRAP),
        "width" to encoded.width,"height" to encoded.height))
    } catch (error: Exception) {
      request?.reject("E_CAMERA_FRAME",error.message ?: "Could not capture frame.",error)
    } finally {
      if (oriented !== original) oriented?.recycle()
      original?.recycle()
      image.close()
    }
  }

  override fun onDetachedFromWindow() {
    detached = true; ready = false; binding++
    keepScreenOn = false
    pending.getAndSet(null)?.reject("E_CAMERA_STOPPED","Camera stopped.",null)
    analysis?.clearAnalyzer()
    analysis?.let { provider?.unbind(it) }
    preview?.let { provider?.unbind(it) }
    analysis = null; preview = null
    executor.shutdown()
    super.onDetachedFromWindow()
  }
}
