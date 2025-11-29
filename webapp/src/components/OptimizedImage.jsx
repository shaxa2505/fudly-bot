import { useState, useRef, useEffect, memo } from 'react';

// Default placeholder - simple gray box with camera emoji
const DEFAULT_PLACEHOLDER = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300"%3E%3Crect fill="%23F5F5F5" width="300" height="300"/%3E%3Ctext x="150" y="160" text-anchor="middle" font-size="48"%3E📷%3C/text%3E%3C/svg%3E';

/**
 * OptimizedImage component with lazy loading and placeholder
 *
 * Features:
 * - Lazy loading with IntersectionObserver
 * - Placeholder while loading
 * - Fade-in animation on load
 * - Error handling with fallback
 * - Blur-up effect option
 */
const OptimizedImage = memo(function OptimizedImage({
  src,
  alt = '',
  className = '',
  placeholder = DEFAULT_PLACEHOLDER,
  width,
  height,
  style = {},
  onLoad,
  onError,
  ...props
}) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [isInView, setIsInView] = useState(false);
  const [hasError, setHasError] = useState(false);
  const imgRef = useRef(null);

  // Use IntersectionObserver for lazy loading
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true);
          observer.disconnect();
        }
      },
      {
        rootMargin: '50px', // Start loading 50px before entering viewport
        threshold: 0.01,
      }
    );

    if (imgRef.current) {
      observer.observe(imgRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleLoad = (e) => {
    setIsLoaded(true);
    onLoad?.(e);
  };

  const handleError = (e) => {
    setHasError(true);
    setIsLoaded(true);
    onError?.(e);
  };

  const imageSrc = hasError ? placeholder : (isInView ? (src || placeholder) : placeholder);

  return (
    <div
      ref={imgRef}
      className={`optimized-image-container ${className}`}
      style={{
        position: 'relative',
        overflow: 'hidden',
        width: width || '100%',
        height: height || 'auto',
        backgroundColor: '#F5F5F5',
        ...style,
      }}
    >
      <img
        src={imageSrc}
        alt={alt}
        className={`optimized-image ${isLoaded ? 'loaded' : 'loading'}`}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          opacity: isLoaded ? 1 : 0.5,
          transition: 'opacity 0.3s ease',
          filter: isLoaded ? 'none' : 'blur(5px)',
        }}
        onLoad={handleLoad}
        onError={handleError}
        loading="lazy"
        decoding="async"
        {...props}
      />
    </div>
  );
});

/**
 * Simple Image component with error handling
 * Lighter than OptimizedImage for simple use cases
 */
export const SimpleImage = memo(function SimpleImage({
  src,
  alt = '',
  fallback = DEFAULT_PLACEHOLDER,
  className = '',
  ...props
}) {
  const [imgSrc, setImgSrc] = useState(src);

  const handleError = () => {
    setImgSrc(fallback);
  };

  // Reset src when prop changes
  useEffect(() => {
    setImgSrc(src);
  }, [src]);

  return (
    <img
      src={imgSrc || fallback}
      alt={alt}
      className={className}
      onError={handleError}
      loading="lazy"
      decoding="async"
      {...props}
    />
  );
});

/**
 * Hook for image preloading
 */
export function useImagePreload(src) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!src) return;

    const img = new Image();

    img.onload = () => {
      setIsLoaded(true);
      setHasError(false);
    };

    img.onerror = () => {
      setHasError(true);
      setIsLoaded(false);
    };

    img.src = src;

    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, [src]);

  return { isLoaded, hasError };
}

/**
 * Preload multiple images
 */
export function preloadImages(srcArray) {
  return Promise.all(
    srcArray.map(
      (src) =>
        new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(src);
          img.onerror = () => reject(src);
          img.src = src;
        })
    )
  );
}

export default OptimizedImage;
